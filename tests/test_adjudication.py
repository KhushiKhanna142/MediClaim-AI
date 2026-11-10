import json

from src.adjudication.engine import decide
from src.adjudication.pipeline import Adjudicator
from src.adjudication.reader import parse_findings
from src.rag.retriever import base_clause_id
from synth.generate import generate
from synth.models import claim_to_dict
from synth.rules import RULESETS
from synth.to_extracted import oracle_extraction, oracle_findings

CLAIMS = [(claim_to_dict(c), t) for c, t in generate(7)]


def test_engine_reproduces_ground_truth_given_perfect_findings():
    checked = 0
    for d, truth in CLAIMS:
        if truth["status"] == "needs_review":
            continue
        out = decide(oracle_extraction(d), oracle_findings(d, RULESETS[d["policy_id"]]))
        assert out["decision"] == truth["status"], d["claim_id"]
        assert abs(out["payable_amount"] - truth["payable_amount"]) < 0.01, d["claim_id"]
        assert set(out["cited_clause_ids"]) == set(truth["expected_clause_ids"]), (d["claim_id"], out["cited_clause_ids"])
        checked += 1
    assert checked == 26


EVIDENCE = {"specified": [{"clause_id": "5.1.2", "text": "x"}], "room": [{"clause_id": "2.13/1", "text": "y"}]}


def test_reader_drops_citations_that_were_not_retrieved():
    reply = json.dumps({"is_specified": True, "spec_clause": "5.1.2", "room_cap_clause": "2.13", "non_payable_clause": "9.9.9",
                        "coverage_clause": "", "initial_waiting_days": "30 days"})
    f, dropped = parse_findings("```json\n" + reply + "\n```", EVIDENCE)
    assert f.spec_clause == "5.1.2" and f.room_cap_clause == "2.13" and f.non_payable_clause is None
    assert f.initial_waiting_days == 30 and dropped == ["non_payable_clause=9.9.9"]


class StubRetriever:
    def search(self, query, k=5, policy_ids=None, mode="hybrid", **kw):
        return [{"clause_id": "5.1.2", "text": "specified disease list"}]


class StubLLM:
    calls = 0

    def complete(self, system, user, max_tokens=300):
        StubLLM.calls += 1
        return json.dumps({"initial_waiting_days": 30, "initial_wait_clause": "5.1.2", "is_specified": False})


def test_pipeline_blocks_before_reading_policy_when_validation_fails():
    d = next(x for x, t in CLAIMS if x["category"] == "missing_docs")
    StubLLM.calls = 0
    out = Adjudicator(StubRetriever(), StubLLM()).run(oracle_extraction(d), d["policy_id"], d["docs_present"])
    assert out["decision"] == "needs_review" and out["flags"][0].startswith("missing_documents") and StubLLM.calls == 0


def test_pipeline_runs_end_to_end_with_stubs():
    d = next(x for x, t in CLAIMS if x["category"] == "clean_approve")
    out = Adjudicator(StubRetriever(), StubLLM()).run(oracle_extraction(d), d["policy_id"], d["docs_present"])
    assert out["decision"] in ("approve", "partial") and out["retrieved_clause_ids"] == ["5.1.2"]


def test_findings_tolerate_null_and_text_booleans():
    from src.adjudication.findings import Findings
    f = Findings.model_validate({"is_specified": None, "is_pre_existing": "Yes", "initial_waiting_days": None})
    assert f.is_specified is False and f.is_pre_existing is True


def test_reader_accepts_bracketed_ids_and_matched_passage():
    from src.adjudication.reader import clean_id, passage
    assert clean_id("[Section C] 32 Surgical Procedures Hernia ...") == "Section C" and clean_id(["[2.13/1]"]) == "2.13/1"
    ev = {"specified": [{"clause_id": "Section C", "text": "SECTION C"}], "room": [{"clause_id": "2.13/1", "text": "y"}]}
    f, dropped = parse_findings(json.dumps({"spec_clause": "[Section C]", "room_cap_clause": "[2.13/1] text", "ped_clause": "[Def.35]"}), ev)
    assert f.spec_clause == "Section C" and f.room_cap_clause == "2.13/1" and dropped == ["ped_clause=Def.35"]
    long_parent = "HEADER " + "x" * 3000
    assert "Hernia" in passage({"text": long_parent, "child_text": "list: Hernia, Cataract"})