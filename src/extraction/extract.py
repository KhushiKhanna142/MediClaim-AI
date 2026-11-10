"""One LLM call turns the OCR'd claim documents into a validated ExtractedClaim.

If the reply fails Pydantic validation, the error is shown to the model once and it is asked to fix the JSON.
Extraction only reads. It makes no coverage decisions and does no arithmetic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from src.baseline.naive import build_claim_text
from src.baseline.ocr import read_claim_docs
from src.extraction.schemas import ExtractedClaim

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
        return self.extract_text(build_claim_text(read_claim_docs(claim_dir)))