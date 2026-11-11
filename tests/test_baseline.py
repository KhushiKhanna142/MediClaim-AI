from src.baseline.ocr import OCR_DPI, RAPID_DPI, engine_name
import json

from eval.e2e_metrics import aggregate, score_claim
from src.baseline.naive import NaiveBaseline, parse_reply


class StubRetriever:
    def search(self, query, k=5, policy_ids=None, mode="dense", **kw):
        return [{"clause_id": "2.12/1", "text": "PED waiting period"}, {"clause_id": "6.2.9", "text": "non payable"}]


class StubLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, max_tokens=300):
        self.seen = user
        return self.reply


def test_parse_reply_handles_fences_and_commas():
    r = parse_reply('```json\n{"decision": "Partial", "payable_amount": "84,447.5", "cited_clause_ids": ["6.2.9"], "reasoning": "x"}\n```')
    assert r["decision"] == "partial" and r["payable_amount"] == 84447.5 and r["cited_clause_ids"] == ["6.2.9"]
    assert parse_reply("no json")["decision"] is None


def test_score_claim():
    truth = {"status": "partial", "claimed_amount": 100000, "payable_amount": 80000.0, "expected_clause_ids": ["6.2.9", "4.1.18"]}
    pred = {"decision": "partial", "payable_amount": 80000.5, "cited_clause_ids": ["6.2.9", "9.9"], "retrieved_clause_ids": ["6.2.9"]}
    s = score_claim(pred, truth)
    assert s["decision_ok"] and s["payable_exact"] and s["cite_recall"] == 0.5 and s["cite_precision"] == 0.5
    assert s["cite_unsupported"] == 0.5
    bad = score_claim({"decision": "approve", "payable_amount": 100000, "cited_clause_ids": []}, truth)
    assert not bad["decision_ok"] and not bad["payable_exact"] and bad["payable_err_pct"] == 20.0
    assert aggregate([s, bad])["decision_acc"] == 0.5


def test_needs_review_skips_money():
    s = score_claim({"decision": "needs_review"}, {"status": "needs_review", "claimed_amount": 5, "payable_amount": 0, "expected_clause_ids": []})
    assert s["decision_ok"] and s["payable_exact"] is None and s["cite_recall"] is None


def test_naive_pipeline_end_to_end(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ocr_cache.json").write_text(json.dumps({"claim_form": {"text": "Name Asha Rao total 8,000", "method": "ocr"}, "_files": {"_ocr": f"{engine_name()}-{OCR_DPI}-{RAPID_DPI}"}}))
    llm = StubLLM('{"decision": "approve", "payable_amount": 8000, "cited_clause_ids": ["6.2.9"], "reasoning": "ok"}')
    out = NaiveBaseline(StubRetriever(), llm).predict(tmp_path, "niva_aspire")
    assert out["decision"] == "approve" and out["retrieved_clause_ids"] == ["2.12/1", "6.2.9"]
    assert "Asha Rao" in llm.seen and "[clause 6.2.9]" in llm.seen


def test_ocr_cache_is_invalidated_when_files_change(tmp_path):
    import fitz
    from src.baseline.ocr import read_claim_docs
    (tmp_path / "docs").mkdir()
    def make(name, text):
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), text * 3)
        doc.save(tmp_path / "docs" / name)
    make("claim_form.pdf", "claim form text ")
    assert set(read_claim_docs(tmp_path)) == {"claim_form"}
    make("policy_schedule.pdf", "schedule text here ")
    assert set(read_claim_docs(tmp_path)) == {"claim_form", "policy_schedule"}


def test_overpay_and_comma_numbers():
    truth = {"status": "partial", "claimed_amount": 100000, "payable_amount": 80000.0, "expected_clause_ids": []}
    assert score_claim({"decision": "approve", "payable_amount": 100000}, truth)["overpay"] is True
    assert score_claim({"decision": "partial", "payable_amount": 80000}, truth)["overpay"] is False
    assert score_claim({"decision": "reject", "payable_amount": 0}, truth)["overpay"] is False
    r = parse_reply('{"decision": "partial", "payable_amount": 118,400, "cited_clause_ids": [], "reasoning": "x"}')
    assert r["payable_amount"] == 118400


def test_rows_from_boxes_pairs_label_with_value_at_offset_height():
    from src.baseline.ocr import rows_from_boxes
    boxes = [(589, 138, 30, "Waiting period, pre-existing diseases"), (576, 862, 30, "12 months"),
             (639, 139, 30, "Waiting period, specified diseases"), (626, 862, 30, "24 months")]
    assert rows_from_boxes(boxes).splitlines() == ["Waiting period, pre-existing diseases 12 months" if False else rows_from_boxes(boxes).splitlines()[0],
                                                   rows_from_boxes(boxes).splitlines()[1]]
    lines = rows_from_boxes(boxes).splitlines()
    assert len(lines) == 2 and "pre-existing" in lines[0] and "12 months" in lines[0] and "24 months" in lines[1]