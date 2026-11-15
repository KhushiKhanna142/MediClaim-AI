"""Judge plumbing tests. A fake LLM answers every judge prompt with a valid object synthesised from the JSON schema embedded in the
prompt, so the real RAGAS and DeepEval metrics run end to end without an API key. The metric tests skip when the libraries are
not installed (they belong in the separate eval venv); the export tests need neither."""
import json

import pytest

from eval.judge_common import JudgeCore, SUFFIX
from eval.judge_export import (STMT_COVERED, STMT_INITIAL_WAIT, STMT_PED, STMT_SPECIFIED, build_clause_lookup, groundedness_rows,
                               result_text, rule_statements)


def synth(schema: dict, defs: dict | None = None):
    """Smallest valid instance of a JSON schema (positive verdicts, one list item)."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return synth(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        return synth(next(s for s in schema["anyOf"] if s.get("type") != "null"), defs)
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        return {k: synth(v, defs) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [synth(schema.get("items", {}), defs)]
    return {"string": "ok", "integer": 1, "number": 1.0, "boolean": True}.get(t, "ok")


class SchemaLLM:
    model = "fake-judge"

    def __init__(self):
        self.prompts = []

    def complete(self, system, user, max_tokens=0, images=None):
        self.prompts.append(user)
        marker = SUFFIX.split("{schema}")[0]
        if marker not in user:
            return "plain text answer"
        return json.dumps(synth(json.loads(user.split(marker)[-1].split("\n\nYour previous")[0])))


class Broken:
    model = "fake"
    n = 0

    def complete(self, system, user, max_tokens=0, images=None):
        self.n += 1
        return "not json" if self.n == 1 else '{"verdict": 1, "reason": "x"}'


# ---------------------------------------------------------------- core (no extra deps)
def test_core_caches_and_survives_restart(tmp_path):
    from pydantic import BaseModel

    class V(BaseModel):
        verdict: int
        reason: str
    llm = SchemaLLM()
    core = JudgeCore(llm, tmp_path / "c.json")
    assert core.structured("p", V).verdict == 1 and core.calls == 1
    core.structured("p", V)
    assert core.calls == 1 and core.cache_hits == 1
    again = JudgeCore(SchemaLLM(), tmp_path / "c.json")          # new process, same cache file
    again.structured("p", V)
    assert again.calls == 0


def test_core_repairs_one_bad_reply(tmp_path):
    from pydantic import BaseModel

    class V(BaseModel):
        verdict: int
        reason: str
    llm = Broken()
    assert JudgeCore(llm, tmp_path / "c.json").structured("p", V).verdict == 1 and llm.n == 2


# ---------------------------------------------------------------- export helpers (no extra deps)
def test_rule_statements_cover_each_rule_without_claim_numbers():
    d = {"decision": "partial", "deductions": [{"rule": "non_payable", "amount": 3450}, {"rule": "sum_insured_cap", "amount": 83800},
                                                {"rule": "proportionate_deduction"}, {"rule": "copay"}, {"rule": "mystery"}]}
    s, unmapped = rule_statements(d)
    assert s[0] == STMT_COVERED and len(s) == 5 and unmapped == ["mystery"]
    assert not any(ch.isdigit() for stmt in s for ch in stmt)       # statements describe rules, never this claim's amounts


def test_rule_statements_for_rejections():
    assert rule_statements({"decision": "reject", "reasons": ["Admission 0 days after policy start falls in the 30-day initial waiting period."]})[0] == [STMT_INITIAL_WAIT]
    s, _ = rule_statements({"decision": "reject", "reasons": ["6 months ... waiting period"], "findings": {"is_specified": True, "is_pre_existing": True}})
    assert s == [STMT_SPECIFIED, STMT_PED]
    assert rule_statements({"decision": "reject", "reasons": ["??"]})[1] == ["reject:unknown_reason"]
    assert rule_statements({"decision": "needs_review"}) == ([], [])


def test_clause_lookup_and_text_key_errors():
    base = lambda c: c.split("~")[0].split("#")[0]
    lk = build_clause_lookup([{"policy_id": "p", "clause_id": "4.1.2~p1", "text": "A"}, {"policy_id": "p", "clause_id": "4.1.2~p2", "text": "B"}], base)
    assert lk == {("p", "4.1.2"): "A\nB"}
    with pytest.raises(KeyError, match="keys are"):
        result_text({"clause_id": "1", "weird": "x"})
    with pytest.raises(TypeError):
        build_clause_lookup({"a": "just text"}, base)


def test_groundedness_rows_flag_citations_with_no_clause_text(tmp_path):
    (tmp_path / "C1").mkdir()
    (tmp_path / "C1" / "claim.json").write_text(json.dumps({"policy_id": "p", "category": "partial_nonpayable"}))
    preds = {"C1": {"decision": "partial", "cited_clause_ids": ["6.2.9", "9.9.9"], "deductions": [{"rule": "non_payable"}]},
             "C2": {"decision": "needs_review", "cited_clause_ids": []}}
    rows = groundedness_rows(preds, tmp_path, {("p", "6.2.9"): "Consumables are not payable."}, lambda c: c)
    assert len(rows) == 1 and rows[0]["contexts"] == ["Consumables are not payable."] and rows[0]["missing_clause_text"] == ["9.9.9"]


# ---------------------------------------------------------------- real RAGAS / DeepEval with the fake judge
def test_ragas_runs_end_to_end(tmp_path):
    pytest.importorskip("ragas.metrics.collections")
    from eval.judge_ragas import run, summarise
    rows = [{"id": "q1", "set": "heldout", "policy_id": "p", "question": "Is air ambulance covered?", "retrieved_clause_ids": ["2.1", "3.1"],
             "retrieved_contexts": ["Air ambulance is covered for emergencies.", "Unrelated text."], "gold_clause_ids": ["2.1"],
             "reference": "Air ambulance is covered for emergencies."},
            {"id": "q2", "set": "tuned", "policy_id": "p", "question": "x", "retrieved_clause_ids": [], "retrieved_contexts": [], "gold_clause_ids": ["1"], "reference": ""}]
    core = JudgeCore(SchemaLLM(), tmp_path / "c.json")
    res = run(rows, core)
    assert 0 <= res["q1"]["context_precision"] <= 1 and 0 <= res["q1"]["context_recall"] <= 1, res
    assert "error" in res["q2"]
    assert core.calls > 0 and "heldout" in summarise(res)
    calls = core.calls
    run(rows, core)
    assert core.calls == calls                                      # second run is fully cached


def test_deepeval_runs_end_to_end(tmp_path):
    pytest.importorskip("deepeval")
    from eval.judge_deepeval import run, summarise
    rows = [{"claim_id": "C007", "category": "partial_nonpayable", "decision": "partial", "cited_clause_ids": ["6.2.9"],
             "statements": [STMT_COVERED, "Non-medical items such as disposables and consumables are not payable."],
             "contexts": ["Consumables are not payable."], "missing_clause_text": [], "unmapped_rules": []},
            {"claim_id": "C099", "category": "x", "decision": "reject", "cited_clause_ids": ["9.9"], "statements": ["s"], "contexts": [],
             "missing_clause_text": ["9.9"], "unmapped_rules": []}]
    res = run(rows, JudgeCore(SchemaLLM(), tmp_path / "c.json"))
    assert "faithfulness" in res["C007"] and 0 <= res["C007"]["faithfulness"] <= 1, res
    assert "error" in res["C099"] and "partial_nonpayable" in summarise(res)