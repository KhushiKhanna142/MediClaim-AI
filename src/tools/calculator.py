"""Deterministic payable-amount calculator.

The LLM never does arithmetic. It picks which rules apply (and cites clause IDs);
this module computes the numbers. It is also the reference used to produce
ground-truth labels for synthetic claims.

Order of operations (configurable per policy via PolicyTerms):
  1. Non-payable categories (e.g. consumables) are removed.
  2. Room rent is capped per day; the excess is deducted.
  3. If room rent was capped, proportionate deduction applies to other
     categories listed in `proportionate_categories`.
  4. Category sub-limits cap what is left.
  5. Deductible is subtracted.
  6. Co-pay percentage is applied to the remainder.
  7. Remaining sum insured caps the final amount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

TWO = Decimal("0.01")


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def money(x) -> Decimal:
    return D(x).quantize(TWO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Item:
    category: str          # room, icu, surgeon, ot, medicine, consumable, investigation, implant, nursing, other
    amount: Decimal
    description: str = ""


@dataclass(frozen=True)
class PolicyTerms:
    sum_insured: Decimal
    room_rent_limit_per_day: Decimal | None = None   # None = no cap
    copay_pct: Decimal = Decimal("0")
    deductible: Decimal = Decimal("0")
    sublimits: dict[str, Decimal] = field(default_factory=dict)          # category -> max payable
    non_payable_categories: frozenset[str] = frozenset({"consumable"})
    proportionate_categories: frozenset[str] = frozenset(
        {"surgeon", "ot", "investigation", "nursing", "other"}
    )
    # rule name -> clause ID in the policy wording, used for citations
    clause_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class Deduction:
    rule: str
    amount: Decimal
    clause_id: str | None
    note: str = ""


@dataclass
class PayableResult:
    claimed: Decimal
    payable: Decimal
    deductions: list[Deduction]
    status: str  # approve | partial | reject


def calculate_payable(
    items: list[Item],
    terms: PolicyTerms,
    room_days: int = 0,
    remaining_sum_insured: Decimal | None = None,
) -> PayableResult:
    cid = terms.clause_ids.get
    claimed = money(sum((i.amount for i in items), Decimal("0")))
    deductions: list[Deduction] = []

    # Working amounts per category
    by_cat: dict[str, Decimal] = {}
    for i in items:
        by_cat[i.category] = by_cat.get(i.category, Decimal("0")) + D(i.amount)

    # 1. Non-payable categories
    for cat in sorted(terms.non_payable_categories):
        amt = by_cat.pop(cat, Decimal("0"))
        if amt > 0:
            deductions.append(Deduction("non_payable", money(amt), cid("non_payable"), cat))

    # 2. Room rent cap
    ratio = Decimal("1")
    room_actual = by_cat.get("room", Decimal("0"))
    limit = terms.room_rent_limit_per_day
    if limit is not None and room_days > 0 and room_actual > 0:
        actual_per_day = room_actual / room_days
        if actual_per_day > limit:
            eligible = limit * room_days
            deductions.append(
                Deduction("room_rent_cap", money(room_actual - eligible), cid("room_rent_cap"))
            )
            by_cat["room"] = eligible
            ratio = limit / actual_per_day

    # 3. Proportionate deduction
    if ratio < 1:
        for cat in sorted(terms.proportionate_categories):
            amt = by_cat.get(cat, Decimal("0"))
            if amt > 0:
                reduced = amt * ratio
                deductions.append(
                    Deduction(
                        "proportionate_deduction", money(amt - reduced),
                        cid("proportionate_deduction"), cat,
                    )
                )
                by_cat[cat] = reduced

    # 4. Sub-limits
    for cat, cap in sorted(terms.sublimits.items()):
        amt = by_cat.get(cat, Decimal("0"))
        if amt > cap:
            deductions.append(Deduction("sublimit", money(amt - cap), cid(f"sublimit:{cat}"), cat))
            by_cat[cat] = D(cap)

    running = sum(by_cat.values(), Decimal("0"))

    # 5. Deductible
    if terms.deductible > 0:
        taken = min(running, terms.deductible)
        deductions.append(Deduction("deductible", money(taken), cid("deductible")))
        running -= taken

    # 6. Co-pay
    if terms.copay_pct > 0 and running > 0:
        copay = running * terms.copay_pct / Decimal("100")
        deductions.append(Deduction("copay", money(copay), cid("copay"), f"{terms.copay_pct}%"))
        running -= copay

    # 7. Sum insured cap
    cap = D(remaining_sum_insured) if remaining_sum_insured is not None else terms.sum_insured
    if running > cap:
        deductions.append(Deduction("sum_insured_cap", money(running - cap), cid("sum_insured_cap")))
        running = cap

    payable = money(running)
    if payable <= 0:
        status = "reject"
    elif payable == claimed:
        status = "approve"
    else:
        status = "partial"
    return PayableResult(claimed, payable, deductions, status)