from datetime import date

import pytest

from synth.generate import EXPECTED_STATUS, PLAN, generate
from synth.models import Claim, Condition, LineItem, Schedule
from synth.reference import adjudicate, coverage_months, months_between
from synth.rules import RULESETS

NIVA, SEC = RULESETS["niva_aspire"], RULESETS["hdfc_optima_secure_current"]
DOCS = ["claim_form", "hospital_bill", "discharge_summary", "id_proof"]


def claim(policy="niva_aspire", start=date(2024, 1, 10), admit=date(2026, 3, 10), kind="illness", specified=False, ped=False,
          ped_m=36, spec_m=24, prior=0, si=500000, items=None, docs=None, stated=None, room_limit=None, room_mod=False,
          eligible="standard_single", claimed="standard_single", days=3):
    items = items or [LineItem("room", "room", days, 4000, days * 4000), LineItem("surgeon", "s", 1, 40000, 40000)]
    return Claim("T1", "t", policy, {"name": "A", "age": 40, "sex": "F"},
                 Schedule(si, start, ped_m, spec_m, room_limit, 0, prior, room_mod, eligible),
                 Condition("x", kind, specified, ped), admit, admit, days, claimed, items,
                 stated if stated is not None else sum(i.amount for i in items), docs or DOCS)


def test_months_between():
    assert months_between(date(2024, 1, 10), date(2026, 3, 10)) == 26
    assert months_between(date(2024, 1, 10), date(2026, 3, 9)) == 25


def test_clean_approve():
    g = adjudicate(claim(), NIVA)
    assert g["status"] == "approve" and g["payable_amount"] == 52000 and g["expected_flags"] == []
    assert g["expected_clause_ids"] == ["4.1.2"]


def test_30day_waiting_rejects_illness_but_not_accident():
    start, admit = date(2026, 2, 20), date(2026, 3, 5)
    assert adjudicate(claim(start=start, admit=admit), NIVA)["status"] == "reject"
    assert adjudicate(claim(start=start, admit=admit), NIVA)["expected_clause_ids"] == ["5.1.3"]
    assert adjudicate(claim(start=start, admit=admit, kind="accident"), NIVA)["status"] == "approve"


def test_30day_exempt_with_more_than_12_months_continuous_coverage():
    g = adjudicate(claim(start=date(2026, 2, 20), admit=date(2026, 3, 5), prior=13), NIVA)
    assert g["status"] == "approve"


def test_specified_disease_waiting_and_continuity_credit():
    c = claim(specified=True, start=date(2025, 9, 1), admit=date(2026, 3, 10), spec_m=24)
    assert adjudicate(c, NIVA)["status"] == "reject" and adjudicate(c, NIVA)["expected_clause_ids"] == ["5.1.2"]
    c2 = claim(specified=True, start=date(2025, 9, 1), admit=date(2026, 3, 10), spec_m=24, prior=20)
    assert adjudicate(c2, NIVA)["status"] == "approve" and coverage_months(c2) == 26


def test_multi_hop_longer_waiting_period_applies():
    c = claim(specified=True, ped=True, start=date(2023, 11, 10), admit=date(2026, 3, 10), ped_m=36, spec_m=24)  # 28 months
    g = adjudicate(c, NIVA)
    assert g["status"] == "reject" and set(g["expected_clause_ids"]) == {"5.1.2", "5.1.1", "2.1.35"}


def test_ped_satisfied_approves():
    assert adjudicate(claim(ped=True, start=date(2022, 1, 1), admit=date(2026, 3, 10), ped_m=36), NIVA)["status"] == "approve"


def test_missing_document_and_total_mismatch_route_to_review():
    g = adjudicate(claim(docs=["claim_form", "hospital_bill", "id_proof"]), NIVA)
    assert g["status"] == "needs_review" and g["expected_flags"] == ["missing_documents:discharge_summary"] and g["payable_amount"] is None
    g = adjudicate(claim(stated=60000), NIVA)
    assert g["status"] == "needs_review" and "total_mismatch" in g["expected_flags"]


def test_room_cap_partial_for_secure():
    items = [LineItem("room", "room", 3, 8000, 24000), LineItem("surgeon", "s", 1, 80000, 80000), LineItem("medicine", "m", 1, 10000, 10000)]
    g = adjudicate(claim("hdfc_optima_secure_current", items=items, days=3, room_limit=5000, claimed="private"), SEC)
    # room 24000 -> 15000 (-9000); surgeon 80000 * 0.625 = 50000 (-30000); medicine untouched
    assert g["status"] == "partial" and g["payable_amount"] == 75000
    assert {d["rule"] for d in g["deductions"]} == {"room_rent_cap", "proportionate_deduction"}
    assert g["expected_clause_ids"] == ["2.13", "1.1"]


def test_niva_room_type_copay():
    g = adjudicate(claim(room_mod=True, eligible="shared", claimed="deluxe"), NIVA)   # 25% on 52000
    assert g["status"] == "partial" and g["payable_amount"] == 39000 and "4.1.18" in g["expected_clause_ids"]
    assert adjudicate(claim(room_mod=True, eligible="standard_single", claimed="standard_single"), NIVA)["status"] == "approve"


def test_sum_insured_cap():
    items = [LineItem("surgeon", "s", 1, 350000, 350000)]
    g = adjudicate(claim(items=items, si=300000), NIVA)
    assert g["status"] == "partial" and g["payable_amount"] == 300000


# ---------------- generator ----------------
@pytest.fixture(scope="module")
def generated():
    return generate(7)


def test_generator_counts_and_determinism(generated):
    assert len(generated) == 2 * sum(n for _, n in PLAN)
    assert [g["status"] for _, g in generated] == [g["status"] for _, g in generate(7)]
    assert [c.claim_id for c, _ in generated] == [c.claim_id for c, _ in generate(7)]
    assert len({c.claim_id for c, _ in generated}) == len(generated)


def test_generator_categories_match_reference_status(generated):
    for c, g in generated:
        assert g["status"] == EXPECTED_STATUS[c.category], (c.claim_id, g["status"], g["reasons"])


def test_ground_truth_is_internally_consistent(generated):
    for c, g in generated:
        if g["status"] in ("approve", "partial"):
            assert 0 < g["payable_amount"] <= g["claimed_amount"]
        elif g["status"] == "reject":
            assert g["payable_amount"] == 0 and g["expected_clause_ids"]
        else:
            assert g["payable_amount"] is None and g["expected_flags"]
        assert c.discharge_date >= c.admission_date and c.schedule.policy_start < c.admission_date


def test_no_claims_near_a_waiting_period_boundary(generated):
    for c, _ in generated:
        if c.condition.kind == "accident":
            continue
        months = coverage_months(c)
        days = (c.admission_date - c.schedule.policy_start).days + 30 * c.schedule.prior_coverage_months
        assert abs(days - 30) > 10 and abs(days - 365) > 20, c.claim_id
        if c.condition.specified:
            assert abs(months - c.schedule.spec_months) >= 3, c.claim_id
        if c.condition.is_ped:
            assert abs(months - c.schedule.ped_months) >= 3, c.claim_id


def test_partial_room_claims_really_exceed_the_limit(generated):
    for c, g in generated:
        if c.category == "partial_room" and c.policy_id == "hdfc_optima_secure_current":
            assert c.items[0].rate > c.schedule.room_limit_per_day
            assert any(d["rule"] == "proportionate_deduction" for d in g["deductions"])