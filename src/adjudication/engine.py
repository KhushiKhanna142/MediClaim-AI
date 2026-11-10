"""Deterministic decision engine. Takes an extracted claim and policy findings; applies waiting periods and calls the
calculator for money. No LLM, no retrieval. Mirrors the order a human adjudicator follows."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.adjudication.findings import Findings
from src.extraction.schemas import ExtractedClaim
from src.tools.calculator import Item, PolicyTerms, calculate_payable

CONTINUITY_EXEMPTS_INITIAL_WAIT_ABOVE_MONTHS = 12   # modelling assumption, documented in the README


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def _uniq(ids):
    out = []
    for i in ids:
        if i and i not in out:
            out.append(i)
    return out


def decide(c: ExtractedClaim, f: Findings) -> dict:
    days = (c.admission_date - c.policy_start).days
    months = months_between(c.policy_start, c.admission_date) + c.continuity_credit_months
    accident = c.cause == "accident"

    if f.initial_waiting_days and not accident and days < f.initial_waiting_days and months <= CONTINUITY_EXEMPTS_INITIAL_WAIT_ABOVE_MONTHS:
        return _out("reject", 0.0, [], _uniq([f.initial_wait_clause]),
                    [f"Admission {days} days after policy start falls in the {f.initial_waiting_days}-day initial waiting period."])

    required, cites = 0, []
    if not accident and f.is_specified:
        required = max(required, c.specified_waiting_months or 0)
        cites.append(f.spec_clause)
    if not accident and f.is_pre_existing:
        required = max(required, c.ped_waiting_months or 0)
        cites += [f.ped_clause, f.ped_def_clause]
    if cites and months < required:
        return _out("reject", 0.0, [], _uniq(cites),
                    [f"{months} months of continuous coverage is below the {required}-month waiting period that applies."])

    extra = f.room_modification_copay_pct or 0 if c.room_type_modification else 0
    mod_applied = extra > 0
    clause_ids = {k: v for k, v in (("room_rent_cap", f.room_cap_clause), ("proportionate_deduction", f.room_cap_clause),
                                    ("copay", f.room_mod_clause if mod_applied else f.copay_clause),
                                    ("non_payable", f.non_payable_clause), ("sum_insured_cap", f.sum_insured_clause)) if v}
    terms = PolicyTerms(sum_insured=Decimal(c.sum_insured),
                        room_rent_limit_per_day=Decimal(c.room_limit_per_day) if c.room_limit_per_day else None,
                        copay_pct=Decimal(c.copay_pct + extra), clause_ids=clause_ids)
    res = calculate_payable([Item(i.category, Decimal(i.amount), i.description) for i in c.items], terms,
                            room_days=(c.discharge_date - c.admission_date).days)
    deductions = [{"rule": d.rule, "amount": float(d.amount), "clause_id": d.clause_id, "note": d.note} for d in res.deductions]
    cites = _uniq([d["clause_id"] for d in deductions] + ([f.coverage_clause] if res.payable > 0 else []))
    if mod_applied and f.room_mod_clause not in cites:
        cites.append(f.room_mod_clause)
    why = "No waiting-period exclusion applies." if res.status == "approve" else \
        "Payable amount reduced by: " + ", ".join(sorted({d['rule'] for d in deductions})) + "."
    return _out(res.status, float(res.payable), deductions, [x for x in cites if x], [why])


def _out(status, payable, deductions, cites, reasons):
    return {"decision": status, "payable_amount": payable, "deductions": deductions,
            "cited_clause_ids": cites, "reasons": reasons}