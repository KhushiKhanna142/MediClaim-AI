from src.validation.checks import validate
from synth.generate import generate
from synth.models import claim_to_dict
from synth.to_extracted import oracle_extraction

CLAIMS = [(claim_to_dict(c), truth) for c, truth in generate(7)]


def test_flags_match_ground_truth_on_every_claim():
    for d, truth in CLAIMS:
        rep = validate(oracle_extraction(d), d["docs_present"])
        assert rep.flags == truth["expected_flags"], (d["claim_id"], rep.flags, rep.details)
        assert rep.needs_review == (truth["status"] == "needs_review")


def test_form_vs_bill_disagreement():
    d = next(x for x, _ in CLAIMS if x["category"] == "clean_approve")
    c = oracle_extraction(d)
    c.claimed_total = c.bill_total + 500
    rep = validate(c, d["docs_present"])
    assert "total_mismatch" in rep.flags and any("claim form" in s for s in rep.details)


def test_date_and_policy_start_checks():
    d = next(x for x, _ in CLAIMS if x["category"] == "clean_approve")
    c = oracle_extraction(d)
    c.admission_date, c.discharge_date = c.discharge_date, c.admission_date
    assert "date_order" in validate(c, d["docs_present"]).flags
    c = oracle_extraction(d)
    c.policy_start = c.admission_date.replace(year=c.admission_date.year + 1)
    assert "admitted_before_policy_start" in validate(c, d["docs_present"]).flags


def test_missing_adjudication_fields_block():
    d = next(x for x, _ in CLAIMS if x["category"] == "clean_approve")
    c = oracle_extraction(d)
    c.sum_insured = None
    assert any(f.startswith("missing_fields:sum_insured") for f in validate(c, d["docs_present"]).flags)