"""Targeted citation retry: reader.refine, the verifier's missing_clause_fields, and the graph loop (a C008-style omission)."""
import json
from typing import Optional

from pydantic import BaseModel

from src.adjudication.findings import Findings
from src.adjudication.reader import PolicyReader
from src.agents.verifier import Verifier
from src.extraction.schemas import ExtractedClaim
from src.graph.workflow import GraphConfig, build_graph, run_claim

HITS = [{"clause_id": "6.2.1", "text": "Admission kit charges.", "child_text": ""},
        {"clause_id": "6.2.9", "text": "Expenses not payable: disposables and consumables listed in List I.", "child_text": ""}]


def claim(**o):
    d = {"patient_name": "A", "diagnosis": "fracture of femur", "cause": "accident", "admission_date": "2025-06-20", "discharge_date": "2025-06-26",
         "claimed_total": 100000, "bill_total": 100000, "sum_insured": 500000, "policy_start": "2025-03-20",
         "items": [{"description": "room", "qty": 6, "amount": 40000, "category": "room"}, {"description": "surgeon", "qty": 1, "amount": 60000, "category": "surgeon"}]}
    d.update(o)
    return d


class Retriever:
    def __init__(self, hits=HITS):
        self.hits, self.queries = hits, []

    def search(self, query, k=3, policy_ids=None, mode="hybrid"):
        self.queries.append((query, k))
        return self.hits


class LLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user, max_tokens=0, images=None):
        self.calls.append(user)
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


def c():
    return ExtractedClaim.model_validate(claim())


# ---------------------------------------------------------------- reader.refine
def test_refine_fills_only_the_requested_empty_field():
    r = PolicyReader(Retriever(), LLM('{"clause": "[6.2.9] Expenses not payable"}'))
    prev = Findings(is_pre_existing=True, ped_clause="5.1.1", initial_waiting_days=30)
    f, trace = r.read(c(), "niva_aspire", refine=["non_payable_clause"], previous=prev)
    assert f.non_payable_clause == "6.2.9" and trace["refined"] == ["non_payable_clause=6.2.9"]
    assert (f.is_pre_existing, f.ped_clause, f.initial_waiting_days) == (True, "5.1.1", 30)       # judgements untouched
    assert trace["retrieved"]["refine:non_payable_clause"] == ["6.2.1", "6.2.9"]


def test_refine_rejects_ids_that_were_not_candidates_and_skips_filled_fields():
    llm = LLM('{"clause": "9.9.9"}')
    r = PolicyReader(Retriever(), llm)
    f, trace = r.read(c(), "p", refine=["non_payable_clause", "coverage_clause"], previous=Findings(coverage_clause="4.1.2"))
    assert f.non_payable_clause is None and trace["dropped_citations"] == ["non_payable_clause=none_found"]
    assert len(llm.calls) == 1                                                                       # coverage_clause was already filled
    assert f.coverage_clause == "4.1.2"


def test_refine_survives_garbled_reply_and_unknown_field():
    r = PolicyReader(Retriever(), LLM("sorry I cannot"))
    f, trace = r.read(c(), "p", refine=["non_payable_clause", "not_a_field"], previous=Findings())
    assert f.non_payable_clause is None and trace["refined"] == []


def test_plain_read_path_is_unchanged():
    full = json.dumps({"initial_waiting_days": 30, "non_payable_clause": "6.2.9", "is_specified": "no"})
    f, trace = PolicyReader(Retriever(), LLM(full)).read(c(), "p")
    assert f.non_payable_clause == "6.2.9" and f.initial_waiting_days == 30 and "non_payable" in trace["retrieved"]


# ---------------------------------------------------------------- verifier
def test_verifier_reports_which_clause_fields_are_missing():
    d = {"decision": "partial", "payable_amount": 96050.0, "cited_clause_ids": ["4.1.2"], "reasons": ["x"],
         "deductions": [{"rule": "non_payable", "amount": 3950.0, "clause_id": None},
                        {"rule": "sum_insured_cap", "amount": 10.0, "clause_id": None}, {"rule": "copay", "amount": 1, "clause_id": "6.1"}]}
    res = Verifier().verify(ExtractedClaim.model_validate(claim()), {}, d, ["4.1.2", "6.1"])
    assert res.missing_clause_fields == ["non_payable_clause", "sum_insured_clause"] and res.to_dict()["missing_clause_fields"]


# ---------------------------------------------------------------- the graph: C008-style omission is repaired without a human
class F(BaseModel):
    initial_waiting_days: int = 30
    is_specified: bool = False
    is_pre_existing: bool = False
    non_payable_clause: Optional[str] = None


class OmittingReader:
    """First read forgets the non-payable clause (as C008 did); a refine call finds it."""
    def __init__(self, can_refine=True):
        self.calls, self.refines, self.can_refine = 0, 0, can_refine

    def read(self, cl, pid, refine=None, previous=None):
        self.calls += 1
        if refine:
            self.refines += 1
            return (F(non_payable_clause="6.2.9") if self.can_refine else previous), {"retrieved": {"refine": ["6.2.9"]}, "dropped_citations": [], "refined": ["x"]}
        return F(), {"retrieved": {"q": ["4.1.2"]}, "dropped_citations": []}


def decide_fn(cl, f):
    cites = ["4.1.2"] + ([f.non_payable_clause] if f.non_payable_clause else [])
    return {"decision": "partial", "payable_amount": 96050.0, "cited_clause_ids": cites, "reasons": ["Payable amount reduced by: non_payable."],
            "deductions": [{"rule": "non_payable", "amount": 3950.0, "clause_id": f.non_payable_clause, "note": "consumable"}]}


def make(reader):
    return build_graph(reader=reader, verifier=Verifier(), decide_fn=decide_fn, findings_cls=F, config=GraphConfig(max_verify_retries=2))


def inputs():
    return {"policy_id": "p", "extracted": claim(), "docs_present": ["claim_form", "hospital_bill", "discharge_summary", "id_proof"]}


def test_missing_clause_is_repaired_by_a_targeted_retry_and_auto_finalises():
    reader = OmittingReader()
    r = run_claim(make(reader), inputs(), "RF1")
    assert r["status"] == "completed" and r["final"]["source"] == "auto"
    assert reader.calls == 2 and reader.refines == 1                      # one full read, one targeted retry
    assert "6.2.9" in r["final"]["cited_clause_ids"]
    assert any(e["node"] == "read_policy" and e["detail"].get("refined") for e in r["state"]["audit"])


def test_if_the_targeted_retry_finds_nothing_the_claim_goes_to_a_human():
    reader = OmittingReader(can_refine=False)
    r = run_claim(make(reader), inputs(), "RF2")
    assert r["status"] == "awaiting_human" and "verifier_failed" in r["packet"]["escalation_reasons"]
    assert reader.calls == 3                                              # first read + 2 capped retries, no endless loop