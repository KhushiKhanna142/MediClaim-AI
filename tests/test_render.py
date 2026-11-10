import json
import random

import fitz

from synth.render import degrade_pdf, inr, render_claim


def test_inr_indian_grouping():
    assert inr(316550) == "3,16,550" and inr(82800) == "82,800" and inr(999) == "999" and inr(1000000) == "10,00,000"


def test_render_and_scan(tmp_path):
    claim = {"claim_id": "T1", "category": "clean_approve", "policy_id": "niva_aspire",
             "patient": {"name": "Asha Rao", "age": 40, "sex": "F"},
             "schedule": {"sum_insured": 1000000, "policy_start": "2022-01-01", "ped_months": 12, "spec_months": 24,
                          "room_limit_per_day": None, "copay_pct": 0, "prior_coverage_months": 0,
                          "room_type_modification": False, "eligible_room": "standard_single"},
             "condition": {"name": "hernia", "kind": "illness", "specified": True, "is_ped": False},
             "admission_date": "2025-02-01", "discharge_date": "2025-02-03", "room_days": 2, "room_claimed": "standard_single",
             "items": [{"category": "room", "description": "Room charges", "qty": 2, "rate": 4000, "amount": 8000}],
             "stated_total": 8000, "docs_present": ["claim_form", "hospital_bill"]}
    d = tmp_path / "T1"
    d.mkdir()
    (d / "claim.json").write_text(json.dumps(claim))
    m = render_claim(d, 7, 1.0)  # everything scanned
    assert {x["doc"] for x in m["docs"]} == {"policy_schedule", "claim_form", "hospital_bill"}
    assert not (d / "docs" / "id_proof.pdf").exists()
    page = fitz.open(d / "docs" / "claim_form.pdf")[0]
    assert page.get_text().strip() == "" and page.get_images()  # image-only, needs OCR
    m2 = render_claim(d, 7, 0.0)
    assert fitz.open(d / "docs" / "claim_form.pdf")[0].get_text().strip() != ""