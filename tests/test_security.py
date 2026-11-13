"""Unit tests for PII detection and masking in src/security/pii.py."""
from __future__ import annotations

import json
from src.extraction.extract import Extractor
from src.security.pii import mask_dict_pii, mask_pii, redact_pii


def test_mask_aadhaar_pan_phone_email_ifsc():
    raw = (
        "Patient: Riya Sharma | Aadhaar: 2345 6789 0123 | PAN: ABCDE1234F | "
        "Mobile: +91 9876543210 | Email: riya.sharma@example.com | IFSC: HDFC0001234"
    )
    masked, counts = mask_pii(raw)

    assert "2345 6789 0123" not in masked
    assert "ABCDE1234F" not in masked
    assert "9876543210" not in masked
    assert "riya.sharma@example.com" not in masked
    assert "HDFC0001234" not in masked

    assert "[AADHAAR_REDACTED]" in masked
    assert "[PAN_REDACTED]" in masked
    assert "[PHONE_REDACTED]" in masked
    assert "[EMAIL_REDACTED]" in masked
    assert "[IFSC_REDACTED]" in masked
    assert counts == {"aadhaar": 1, "pan": 1, "ifsc": 1, "email": 1, "phone": 1}


def test_preserves_amounts_dates_and_clause_ids():
    raw = (
        "Sum Insured: Rs 10,00,000 (1000000) | Bill Total: 82800 | "
        "Admission: 2025-02-19 | Clause 4.1.2 | Policy: NBHHLIP26049V022526"
    )
    masked, counts = mask_pii(raw)
    assert masked == raw
    assert counts == {}


def test_mask_dict_pii():
    data = {
        "diagnosis": "Pneumonia",
        "known_history": "Contact 9876543210 or patient@mail.com",
        "items": [{"description": "Room rent", "amount": 12000}],
    }
    masked = mask_dict_pii(data)
    assert masked["diagnosis"] == "Pneumonia"
    assert "[PHONE_REDACTED]" in masked["known_history"]
    assert "[EMAIL_REDACTED]" in masked["known_history"]
    assert masked["items"][0]["amount"] == 12000


def test_extractor_masks_pii_before_llm_call():
    seen_prompts = []

    class RecordingLLM:
        def complete(self, system, user, **kwargs):
            seen_prompts.append(user)
            return json.dumps({
                "patient_name": "Riya Sharma",
                "diagnosis": "Appendicitis",
                "admission_date": "2025-02-19",
                "discharge_date": "2025-02-21",
                "claimed_total": 50000,
                "bill_total": 50000,
            })

    ext = Extractor(RecordingLLM())
    ext.extract_text(
        "Name: Riya Sharma | Aadhaar: 3456-7890-1234 | PAN: ZYXWV9876K | "
        "Phone: 9876543210 | Diagnosis: Appendicitis | Bill: 50000"
    )

    assert len(seen_prompts) == 1
    sent = seen_prompts[0]
    assert "3456-7890-1234" not in sent
    assert "ZYXWV9876K" not in sent
    assert "9876543210" not in sent
    assert "[AADHAAR_REDACTED]" in sent
    assert "[PAN_REDACTED]" in sent
    assert "[PHONE_REDACTED]" in sent

