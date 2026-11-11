import json

from eval.extraction_eval import score_extraction
from src.extraction.extract import Extractor
from src.extraction.schemas import ExtractedClaim

GOOD = {"patient_name": "Asha Rao", "age": "40", "sex": "Female", "diagnosis": "hernia", "cause": "illness",
        "admission_date": "01/02/2025", "discharge_date": "2025-02-03", "room_category_claimed": "Standard Single",
        "claimed_total": "8,000", "bill_total": 8000,
        "items": [{"description": "Room charges", "qty": "2", "rate": "4,000", "amount": "8,000", "category": "room"}],
        "sum_insured": "10,00,000", "policy_start": "2022-01-01", "room_limit_per_day": None}


class Seq:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, max_tokens=300):
        self.calls += 1
        return self.replies.pop(0)


def test_schema_normalises_messy_values():
    c = ExtractedClaim.model_validate(GOOD)
    assert c.age == 40 and c.sex == "F" and c.claimed_total == 8000 and c.sum_insured == 1000000
    assert str(c.admission_date) == "2025-02-01" and c.room_category_claimed == "standard_single"
    assert c.items[0].amount == 8000 and c.items[0].rate == 4000


def test_extractor_repairs_once():
    llm = Seq("```json\n" + json.dumps({**GOOD, "items": [{"description": "x", "amount": 5, "category": "bogus"}]}) + "\n```",
              json.dumps(GOOD))
    out = Extractor(llm).extract_text("text")
    assert llm.calls == 2 and out.patient_name == "Asha Rao"


def test_score_extraction():
    truth = {"patient": {"name": "Asha Rao", "age": 40, "sex": "F"}, "condition": {"name": "hernia", "kind": "illness"},
             "admission_date": "2025-02-01", "discharge_date": "2025-02-03", "room_claimed": "standard_single", "stated_total": 8000,
             "schedule": {"sum_insured": 1000000, "policy_start": "2022-01-01", "ped_months": 12, "spec_months": 24, "room_limit_per_day": None,
                          "copay_pct": 0, "prior_coverage_months": 0, "room_type_modification": False, "eligible_room": "standard_single"},
             "items": [{"category": "room", "description": "Room", "qty": 2, "rate": 4000, "amount": 8000}]}
    pred = json.loads(ExtractedClaim.model_validate({**GOOD, "ped_waiting_months": 12, "specified_waiting_months": 24,
                                                     "eligible_room": "standard single"}).model_dump_json())
    s = score_extraction(pred, truth)
    assert s["patient_name"] and s["admission_date"] and s["room_limit_per_day"] and s["item_recall"] == 1.0 and s["item_category_acc"] == 1.0


def test_null_copay_and_continuity_mean_zero():
    c = ExtractedClaim.model_validate({**GOOD, "copay_pct": None, "continuity_credit_months": "Nil", "room_type_modification": None})
    assert c.copay_pct == 0 and c.continuity_credit_months == 0 and c.room_type_modification is False