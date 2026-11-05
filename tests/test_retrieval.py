import json
from datetime import date

from eval.retrieval_eval import evaluate
from src.rag.index import build_index
from src.rag.retriever import HybridRetriever, base_clause_id


def _rec(pid, insurer, cid, text, typ="parent", **kw):
    base = {"policy_id": pid, "insurer": insurer, "product": "P", "uin": "U", "status": "current",
            "effective_from": kw.get("effective_from"), "effective_to": kw.get("effective_to"),
            "source_type": "insurer_policy", "clause_id": cid, "section": "S", "page_start": 1, "page_end": 1}
    if typ == "parent":
        return {**base, "type": "parent", "chunk_id": f"{pid}::{cid}", "text": text}
    return {**base, "type": "child", "chunk_id": f"{pid}::{cid}::c1", "parent_id": f"{pid}::{cid}",
            "context": f"{insurer} | P | {cid} | S", "text": text}


def make(tmp_path):
    rows = []
    corpus = [("a", "Alpha Insurer", "2.1.7", "Co-payment means a cost sharing requirement where the insured bears a percentage of the claim"),
              ("a", "Alpha Insurer", "2.1.42", "Room Rent means the amount charged by a hospital towards room and boarding expenses"),
              ("a", "Alpha Insurer", "5.1.3", "Thirty day waiting period applies to any illness in the first thirty days of the policy"),
              ("b", "Beta Insurer", "Def.8", "Co-payment is a fixed ten percent share of every admissible claim paid by the insured"),
              ("b", "Beta Insurer", "Def.43", "Room Rent charges are limited to one percent of the sum insured per day"),
              ("b", "Beta Insurer", "Def.9", "Zebra unrelated clause about premium refund on cancellation of the policy")]
    for pid, ins, cid, text in corpus:
        rows += [_rec(pid, ins, cid, text), _rec(pid, ins, cid, text, "child")]
    (tmp_path / "x.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    client, emb, children, parents = build_index(str(tmp_path), ":memory:", "hash")
    return HybridRetriever(client, emb, children, parents)


def test_policy_filter_never_leaks(tmp_path):
    r = make(tmp_path)
    for mode in ("dense", "bm25", "hybrid"):
        res = r.search("co-payment cost sharing", k=5, policy_ids=["a"], mode=mode)
        assert res and all(x["policy_id"] == "a" for x in res)
    res = r.search("room rent", k=3, policy_ids=["b"])
    assert res[0]["clause_id"] == "Def.43"


def test_hybrid_finds_expected_clause_and_expands_to_parent(tmp_path):
    r = make(tmp_path)
    res = r.search("thirty day waiting period", k=3, policy_ids=["a"])
    assert res[0]["clause_id"] == "5.1.3" and res[0]["text"].startswith("Thirty day")


def test_date_filter(tmp_path):
    rows = [_rec("old", "Alpha Insurer", "1", "Room rent limit is one percent", effective_from="2020-01-01", effective_to="2022-12-31"),
            _rec("old", "Alpha Insurer", "1", "Room rent limit is one percent", "child", effective_from="2020-01-01", effective_to="2022-12-31"),
            _rec("new", "Alpha Insurer", "1", "Room rent limit is two percent", effective_from="2023-01-01"),
            _rec("new", "Alpha Insurer", "1", "Room rent limit is two percent", "child", effective_from="2023-01-01")]
    (tmp_path / "x.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    client, emb, ch, pa = build_index(str(tmp_path), ":memory:", "hash")
    r = HybridRetriever(client, emb, ch, pa)
    assert {x["policy_id"] for x in r.search("room rent limit", as_of=date(2021, 6, 1))} == {"old"}
    assert {x["policy_id"] for x in r.search("room rent limit", as_of=date(2024, 6, 1))} == {"new"}


def test_eval_metrics(tmp_path):
    r = make(tmp_path)
    qs = [{"id": "q1", "question": "co-payment cost sharing percentage", "policy_id": "a", "gold_clause_ids": ["2.1.7"]},
          {"id": "q2", "question": "room rent boarding", "policy_id": "b", "gold_clause_ids": ["Def.43"]},
          {"id": "q3", "question": "something with no match xyzzy", "policy_id": "a", "gold_clause_ids": ["9.9.9"]}]
    m, misses = evaluate(r, qs, "hybrid")
    assert m["recall@1"] == 2 / 3 and abs(m["mrr"] - 2 / 3) < 1e-9 and len(misses) == 1


def test_base_clause_id():
    assert base_clause_id("2.1.7") == "2.1.7" and base_clause_id("Section C/XI#2~p3") == "Section C/XI"


def test_rerank_mode_reorders_and_respects_policy(tmp_path):
    import pytest
    r = make(tmp_path)
    with pytest.raises(ValueError):
        r.search("room rent", policy_ids=["b"], mode="hybrid_rerank")

    class ZebraFirst:
        def score(self, q, passages):
            return [1.0 if "Zebra" in p else 0.0 for p in passages]

    r.reranker = ZebraFirst()
    res = r.search("room rent", k=3, policy_ids=["b"], mode="hybrid_rerank")
    assert res[0]["clause_id"] == "Def.9" and all(x["policy_id"] == "b" for x in res)