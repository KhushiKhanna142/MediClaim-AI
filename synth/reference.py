"""Reference adjudicator: deterministic ground truth for synthetic claims. Never calls an LLM.

Order: required documents -> bill arithmetic -> waiting-period exclusions -> payable amount via src.tools.calculator.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.tools.calculator import Item, PolicyTerms, calculate_payable
from synth.models import REQUIRED_DOCS, Claim
from synth.rules import RuleSet


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def coverage_months(c: Claim) -> int:
    """Months of continuous coverage at admission, including ported prior coverage."""
    return months_between(c.schedule.policy_start, c.admission_date) + c.schedule.prior_coverage_months


def _uniq(ids):
    out = []
    for i in ids:
        if i and i not in out:
            out.append(i)
    return out


def adjudicate(c: Claim, r: RuleSet) -> dict:
    flags: list[str] = []
    reasons: list[str] = []

    missing = [d for d in REQUIRED_DOCS if d not in c.docs_present]
    computed = sum(i.amount for i in c.items)
    if missing:
        flags.append("missing_documents:" + ",".join(missing))
    if abs(computed - c.stated_total) > 1:
        flags.append("total_mismatch")
    if flags:
        reasons.append("Validation failed before adjudication; route to human review.")
        return _result("needs_review", c, None, [], [], flags, reasons, r)

    days = (c.admission_date - c.schedule.policy_start).days
    months = coverage_months(c)
    cond = c.condition

    # 30-day waiting period (illness and cancer; accidents are exempt; >12 months continuous coverage is exempt)
    if cond.kind != "accident" and days < 30 and months <= 12:
        reasons.append(f"Admission {days} days after policy start falls in the 30-day waiting period.")
        return _result("reject", c, 0, [], _uniq([r.wait30_clause]), [], reasons, r)

    required, cites = 0, []
    if cond.kind == "illness" and cond.specified:
        required = max(required, c.schedule.spec_months)
        cites.append(r.spec_clause)
    if cond.kind != "accident" and cond.is_ped:
        required = max(required, c.schedule.ped_months)
        cites += [r.ped_clause, r.ped_def_clause]
    if cites and months < required:
        reasons.append(f"{months} months of continuous coverage is below the {required}-month waiting period that applies.")
        return _result("reject", c, 0, [], _uniq(cites), [], reasons, r)

    # payable amount
    extra_copay, room_mod_applied = 0, False
    if c.schedule.room_type_modification:
        for eligible, claimed, pct in r.room_type_copay:
            if c.schedule.eligible_room == eligible and c.room_claimed == claimed:
                extra_copay, room_mod_applied = pct, True
    copay = c.schedule.copay_pct + extra_copay
    clause_ids = {}
    for key, val in (("room_rent_cap", r.room_cap_clause), ("proportionate_deduction", r.room_cap_clause),
                     ("copay", r.room_mod_clause if room_mod_applied else r.copay_clause),
                     ("non_payable", r.nonpayable_clause), ("sum_insured_cap", r.sum_insured_clause)):
        if val:
            clause_ids[key] = val
    terms = PolicyTerms(
        sum_insured=Decimal(c.schedule.sum_insured),
        room_rent_limit_per_day=Decimal(c.schedule.room_limit_per_day) if c.schedule.room_limit_per_day else None,
        copay_pct=Decimal(copay), proportionate_categories=r.proportionate_categories, clause_ids=clause_ids)
    res = calculate_payable([Item(i.category, Decimal(i.amount), i.description) for i in c.items], terms, room_days=c.room_days)
    deductions = [{"rule": d.rule, "amount": float(d.amount), "clause_id": d.clause_id, "note": d.note} for d in res.deductions]
    cites = _uniq([d["clause_id"] for d in deductions] + ([r.coverage_clause] if res.payable > 0 else []))
    if room_mod_applied and r.room_mod_clause not in cites:
        cites.append(r.room_mod_clause)
    reasons.append("No waiting-period exclusion applies." if res.status == "approve"
                   else "Payable amount reduced by: " + ", ".join(sorted({d['rule'] for d in deductions})) + ".")
    return _result(res.status, c, float(res.payable), deductions, cites, [], reasons, r)


def _result(status, c, payable, deductions, clause_ids, flags, reasons, r):
    return {"claim_id": c.claim_id, "category": c.category, "policy_id": c.policy_id, "status": status,
            "claimed_amount": c.stated_total, "payable_amount": payable, "deductions": deductions,
            "expected_clause_ids": clause_ids, "expected_flags": flags, "reasons": reasons,
            "coverage_months_at_admission": coverage_months(c), "assumptions": list(r.assumptions)}