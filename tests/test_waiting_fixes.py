"""Waiting-period handling: accident claims are not blocked on unreadable waiting cells, and OCR retries pages
whose waiting-period rows lost their values. Self-contained: builds claims from a minimal dict."""
import src.baseline.ocr as ocr
from src.extraction.schemas import ExtractedClaim
from src.validation.checks import validate

DOCS = ["claim_form", "hospital_bill", "discharge_summary", "id_proof"]


def claim(cause, ped=None, spec=None):
    return ExtractedClaim.model_validate({
        "patient_name": "A", "diagnosis": "d", "cause": cause, "admission_date": "2025-06-20", "discharge_date": "2025-06-26",
        "claimed_total": 100, "bill_total": 100, "items": [{"description": "room", "qty": 6, "amount": 100, "category": "room"}],
        "sum_insured": 500000, "policy_start": "2025-03-20", "ped_waiting_months": ped, "specified_waiting_months": spec})


def test_accident_not_blocked_by_missing_waiting_months():
    assert validate(claim("accident"), DOCS).flags == []


def test_illness_still_blocked_by_missing_waiting_months():
    r = validate(claim("illness"), DOCS)
    assert r.flags == ["missing_fields:ped_waiting_months,specified_waiting_months"]


def test_illness_partial_missing_names_only_missing():
    assert validate(claim("illness", ped=24), DOCS).flags == ["missing_fields:specified_waiting_months"]


def test_accident_missing_sum_insured_still_blocked():
    c = claim("accident").model_copy(update={"sum_insured": None})
    assert validate(c, DOCS).flags == ["missing_fields:sum_insured"]


BAD = "Policy start date 20/03/2025\nWaiting period,pre-existing diseas months\nWaiting perlod,specified diseases/ecedures\nInitial waiting period 30 days (not applicable to accidents)\nRoom rent limit No limit"
GOOD = BAD.replace("diseas months", "diseases 24 months").replace("diseases/ecedures", "diseases/procedures 12 months")


def test_detects_dropped_values_and_ignores_initial_row():
    assert ocr.waiting_rows_missing_values(BAD) == 2
    assert ocr.waiting_rows_missing_values(GOOD) == 0
    assert ocr.waiting_rows_missing_values("Waiting period,pre-existing diseasasmonths") == 1


def test_retries_at_higher_dpi_until_values_recovered(monkeypatch):
    calls = []
    reads = {200: BAD, 300: BAD, 400: GOOD}
    monkeypatch.setattr(ocr, "_rapid_page_text", lambda page, dpi: calls.append(dpi) or reads[dpi])
    assert ocr.robust_rapid_text(object()) == GOOD
    assert calls == [200, 300, 400]


def test_no_retry_when_first_read_is_clean(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "_rapid_page_text", lambda page, dpi: calls.append(dpi) or GOOD)
    ocr.robust_rapid_text(object())
    assert calls == [200]


def test_keeps_original_when_retries_do_not_help(monkeypatch):
    monkeypatch.setattr(ocr, "_rapid_page_text", lambda page, dpi: BAD)
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    assert ocr.robust_rapid_text(object()) == BAD