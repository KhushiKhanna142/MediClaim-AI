"""Deterministic checks on an extracted claim. No LLM. Runs before adjudication.

Blocking flags mean the claim cannot be adjudicated automatically and goes to human review. They use the same codes
as the ground truth ('missing_documents:<names>', 'total_mismatch'). Warnings are recorded but do not block.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.extraction.schemas import ExtractedClaim

REQUIRED_DOCS = ("claim_form", "hospital_bill", "discharge_summary", "id_proof")
TOLERANCE = 1   # rupees; rounding on bills


@dataclass
class ValidationReport:
    flags: list[str] = field(default_factory=list)       # blocking
    warnings: list[str] = field(default_factory=list)    # informational
    details: list[str] = field(default_factory=list)     # human readable, one per flag or warning

    @property
    def needs_review(self) -> bool:
        return bool(self.flags)


def docs_in_dir(claim_dir: Path) -> list[str]:
    return sorted(p.stem for p in (claim_dir / "docs").glob("*.pdf"))


def validate(c: ExtractedClaim, docs_present: list[str]) -> ValidationReport:
    r = ValidationReport()

    missing = [d for d in REQUIRED_DOCS if d not in docs_present]
    if missing:
        r.flags.append("missing_documents:" + ",".join(missing))
        r.details.append(f"Required documents not submitted: {', '.join(missing)}.")

    items_sum = sum(i.amount for i in c.items)
    mismatches = []
    if c.bill_total is not None and abs(items_sum - c.bill_total) > TOLERANCE:
        mismatches.append(f"bill line items add up to {items_sum} but the bill total is {c.bill_total}")
    if c.bill_total is not None and c.claimed_total is not None and abs(c.bill_total - c.claimed_total) > TOLERANCE:
        mismatches.append(f"claim form says {c.claimed_total} but the bill total is {c.bill_total}")
    if c.bill_total is None and c.claimed_total is not None and abs(items_sum - c.claimed_total) > TOLERANCE:
        mismatches.append(f"bill line items add up to {items_sum} but the claim form says {c.claimed_total}")
    if mismatches:
        r.flags.append("total_mismatch")
        r.details.extend(mismatches)

    if c.discharge_date < c.admission_date:
        r.flags.append("date_order")
        r.details.append("Discharge date is before admission date.")
    if c.policy_start and c.admission_date < c.policy_start:
        r.flags.append("admitted_before_policy_start")
        r.details.append("Admission date is before the policy start date.")

    needed = {"sum_insured": c.sum_insured, "policy_start": c.policy_start,
              "ped_waiting_months": c.ped_waiting_months, "specified_waiting_months": c.specified_waiting_months}
    absent = [k for k, v in needed.items() if v is None]
    if absent:
        r.flags.append("missing_fields:" + ",".join(absent))
        r.details.append(f"Fields needed for adjudication could not be read: {', '.join(absent)}.")

    stay = (c.discharge_date - c.admission_date).days
    if c.length_of_stay_days is not None and c.length_of_stay_days != stay:
        r.warnings.append("stay_length_mismatch")
        r.details.append(f"Discharge summary says {c.length_of_stay_days} day(s) but the dates give {stay}.")
    room_qty = sum(i.qty for i in c.items if i.category in ("room", "icu"))
    if room_qty and room_qty != stay and "date_order" not in r.flags:
        r.warnings.append("room_days_mismatch")
        r.details.append(f"Bill charges {room_qty} room day(s) but the stay is {stay} day(s).")
    return r