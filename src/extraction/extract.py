"""One LLM call turns the OCR'd claim documents into a validated ExtractedClaim.

If the reply fails Pydantic validation, the error is shown to the model once and it is asked to fix the JSON.
Extraction only reads. It makes no coverage decisions and does no arithmetic.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from src.baseline.naive import build_claim_text
from src.baseline.ocr import page_images, read_claim_docs
from src.extraction.schemas import ExtractedClaim

log = logging.getLogger(__name__)

SYSTEM = """You extract structured data from Indian health insurance claim documents (claim form, policy schedule, discharge summary, hospital bill, ID proof). The text may contain OCR errors; read carefully.
Return one JSON object and nothing else. Rules:
- Copy values exactly as written. Never guess a value that is not in the documents: use null.
- Dates as YYYY-MM-DD. Money as whole rupees without commas or currency symbols. sex is M or F.
- cause is "accident" only if the discharge summary says the patient presented after an accident or injury, otherwise "illness".
- known_history: copy the history statement from the discharge summary; history_onset_date: the date it says a condition was diagnosed, else null.
- room_limit_per_day is null when the schedule says no limit. copay_pct is 0 when Nil. continuity_credit_months is 0 when None.
- items: every line of the hospital bill (not subtotals or totals). category is one of: room, icu, surgeon, ot, medicine, consumable, investigation, implant, nursing, other.
  consumable means disposables such as gloves, syringes, masks, admission kits and similar non-medical items; medicine means drugs and pharmacy.
- Policy schedule labels map to keys as follows: "Waiting period, pre-existing diseases" -> ped_waiting_months (number of months);
  "Waiting period, specified diseases/procedures" -> specified_waiting_months; "Room rent limit" -> room_limit_per_day;
  "Eligible room category" -> eligible_room; "Co-payment" -> copay_pct; "Continuity credit (portability)" -> continuity_credit_months;
  "Sum insured" -> sum_insured; "Policy start date" -> policy_start. A "Room type modification" row that says Opted means
  room_type_modification is true; if the row is absent it is false.
- claimed_total comes from the claim form; bill_total from the printed grand total on the bill. They may differ; report each as written.
Keys: patient_name, age, sex, policy_number, hospital, diagnosis, cause, known_history, history_onset_date, admission_date, discharge_date,
length_of_stay_days, room_category_claimed, claimed_total, bill_total, items[{description, qty, rate, amount, category}], sum_insured,
policy_start, ped_waiting_months, specified_waiting_months, room_limit_per_day, copay_pct, continuity_credit_months,
room_type_modification (true/false), eligible_room."""


REQUIRED_FIELDS = ("ped_waiting_months", "specified_waiting_months", "sum_insured", "policy_start")
ALWAYS_REQUIRED = ("sum_insured", "policy_start")
WAITING_FIELDS = ("ped_waiting_months", "specified_waiting_months")


def required_fields(claim: ExtractedClaim) -> tuple[str, ...]:
    """Waiting periods only matter for illness claims: the engine ignores them when cause == accident,
    so an unreadable waiting-period cell must not push an accident claim to human review."""
    return ALWAYS_REQUIRED if claim.cause == "accident" else ALWAYS_REQUIRED + WAITING_FIELDS

FIELD_HELP = {"ped_waiting_months": "waiting period for pre-existing diseases, in months (whole number)",
              "specified_waiting_months": "waiting period for specified diseases/procedures, in months (whole number)",
              "sum_insured": "sum insured in rupees, digits only", "policy_start": "policy start date as YYYY-MM-DD"}
VISION_SYSTEM = """You read scanned Indian health insurance documents. Look at the page images and read ONLY the requested values.
Return one JSON object with exactly the requested keys. Use null for a value you cannot read with certainty; never guess."""
MAX_VISION_IMAGES = 3


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


class Extractor:
    def __init__(self, llm):
        self.llm = llm

    def extract_text(self, claim_text: str) -> ExtractedClaim:
        user = f"CLAIM DOCUMENTS\n{claim_text}\n\nExtract the JSON."
        reply = self.llm.complete(SYSTEM, user, max_tokens=2500)
        try:
            return ExtractedClaim.model_validate(parse_json(reply))
        except (ValidationError, ValueError) as first:
            fix = f"{user}\n\nYour previous reply was:\n{reply[:3000]}\n\nIt was rejected: {str(first)[:800]}\nReturn corrected JSON only."
            return ExtractedClaim.model_validate(parse_json(self.llm.complete(SYSTEM, fix, max_tokens=2500)))

    def extract_dir(self, claim_dir: Path) -> ExtractedClaim:
        docs = read_claim_docs(claim_dir)
        claim = self.extract_text(build_claim_text(docs))
        return self.fill_with_vision(claim, claim_dir, docs)

    def fill_with_vision(self, claim: ExtractedClaim, claim_dir: Path, docs: dict) -> ExtractedClaim:
        """When OCR left a required field empty, ask a vision model to read just those fields from the scanned pages.

        Each value is read twice with differently worded prompts and kept only if both reads agree; a field the
        model cannot read consistently stays None so the claim goes to review instead of acting on a guess.
        Failures are logged (never silently swallowed) and never break extraction."""
        missing = [f for f in required_fields(claim) if getattr(claim, f) is None]
        scanned = sorted((n for n, d in docs.items() if d.get("method") == "ocr"), key=lambda n: n != "policy_schedule")
        if not missing:
            return claim
        if not scanned:
            log.warning("vision fallback skipped: %s missing but no OCR'd page to read (labels may be worded differently)", missing)
            return claim
        images: list[bytes] = []
        for name in scanned:
            images += page_images(claim_dir / "docs" / f"{name}.pdf", max_pages=1)
            if len(images) >= MAX_VISION_IMAGES:
                break
        images = images[:MAX_VISION_IMAGES]
        asks = ["Read these values:\n" + "\n".join(f"- {f}: {FIELD_HELP[f]}" for f in missing),
                "For each item below, find its row in the policy schedule table and report the number printed in that row's "
                "value cell. If the cell is empty or unreadable, return null.\n" + "\n".join(f"- {f}: {FIELD_HELP[f]}" for f in missing)]
        reads = []
        for ask in asks:
            try:
                reads.append(parse_json(self.llm.complete(VISION_SYSTEM, ask, max_tokens=300, images=images)))
            except Exception as exc:  # noqa: BLE001 - a failed fallback must never break extraction
                log.warning("vision read failed for %s: %r", missing, exc)
        if len(reads) < 2:
            return claim
        filled = {f: reads[0][f] for f in missing if reads[0].get(f) is not None and reads[0].get(f) == reads[1].get(f)}
        for f in missing:
            if f not in filled:
                log.warning("vision reads disagree or are empty for %s: %r vs %r", f, reads[0].get(f), reads[1].get(f))
        if not filled:
            return claim
        try:
            return ExtractedClaim.model_validate({**claim.model_dump(), **filled, "vision_filled": sorted(filled)})
        except ValidationError as exc:
            log.warning("vision values rejected by schema: %s", exc)
            return claim