"""Held-out retrieval evaluation for data/golden_set/heldout_questions.jsonl.

Runs the best-available pipeline (hybrid + reranker, optionally + query-rewriter)
against the ten held-out questions that were frozen BEFORE any retrieval results
were inspected on them.

Integrity: the SHA-256 of the questions file is printed in the report header so
anyone can verify the file has not changed between runs.

CLI (from repo root):
    python -m eval.heldout_eval
    python -m eval.heldout_eval --rewrite          # adds LLM query rewriting
    python -m eval.heldout_eval --no-rerank        # skip cross-encoder
    python -m eval.heldout_eval --questions path/to/other.jsonl

Output format example:
    ============================================================
    HELD-OUT RETRIEVAL EVALUATION
    questions : data/golden_set/heldout_questions.jsonl
    sha256    : a3f1...
    n         : 10  (small sample – treat counts as primary)
    pipeline  : hybrid_rerank
    ============================================================

    Per-policy results (k = 1, 3, 5)
      policy                           n   @1   @3   @5   mrr
      niva_aspire                      2    1    2    2  0.750
      hdfc_optima_secure_current       3    2    3    3  0.806
      hdfc_optima_restore_current      1    0    1    1  0.333
      care_supreme_current             1    1    1    1  1.000
      star_comprehensive_current       3    1    3    3  0.667
      ─────────────────────────────────────────────────────────
      TOTAL                           10    5    10  10  0.717

    Raw counts  recall@1 5/10  recall@3 10/10  recall@5 10/10
    Percentage  recall@1 50.0%  recall@3 100.0%  recall@5 100.0%  mrr 0.717

    Misses (rank > 3 or not found):
      ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from src.rag.index import DEFAULT_MODEL, build_index
from src.rag.reranker import get_reranker
from src.rag.retriever import HybridRetriever, base_clause_id

KS = (1, 3, 5)
DEFAULT_QUESTIONS = "data/golden_set/heldout_questions.jsonl"


def _sha256(path: str) -> str:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return h


def _search_one(retr: HybridRetriever, q: dict, mode: str, k: int, rewriter) -> tuple[int | None, list[str]]:
    base_mode = mode[:-3] if mode.endswith("_rw") else mode
    extra = rewriter(q["question"]) if mode.endswith("_rw") and rewriter else None
    res = retr.search(
        q["question"], k=k,
        policy_ids=[q["policy_id"]] if q.get("policy_id") else None,
        mode=base_mode, extra_queries=extra,
    )
    gold = set(q["gold_clause_ids"])
    rank = next((i for i, r in enumerate(res, 1) if base_clause_id(r["clause_id"]) in gold), None)
    top3 = [r["clause_id"] for r in res[:3]]
    return rank, top3


def evaluate(retr: HybridRetriever, questions: list[dict], mode: str, k: int = 10, rewriter=None):
    ranks, misses = [], []
    per_policy: dict[str, list[int | None]] = defaultdict(list)
    for q in questions:
        rank, top3 = _search_one(retr, q, mode, k, rewriter)
        ranks.append(rank)
        per_policy[q["policy_id"]].append(rank)
        if rank is None or rank > 3:
            misses.append((q["id"], q["question"], sorted(q["gold_clause_ids"]), top3, rank))
    return ranks, per_policy, misses


def _metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    out = {f"recall@{kk}": sum(1 for r in ranks if r and r <= kk) for kk in KS}
    out["mrr"] = sum(1 / r for r in ranks if r) / n if n else 0.0
    out["n"] = n
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Held-out retrieval evaluation (frozen question set).")
    ap.add_argument("--questions", default=DEFAULT_QUESTIONS)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--path", default="data/qdrant")
    ap.add_argument("--reranker", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--rewrite", action="store_true", help="enable LLM query-rewriting (needs API key)")
    a = ap.parse_args()

    qpath = Path(a.questions)
    questions = [json.loads(l) for l in qpath.read_text().splitlines() if l.strip()]
    sha = _sha256(a.questions)

    # Pick the best available pipeline name (matches retrieval_eval.py naming)
    if a.no_rerank:
        mode = "hybrid_rw" if a.rewrite else "hybrid"
    else:
        mode = "hybrid_rerank_rw" if a.rewrite else "hybrid_rerank"

    client, emb, children, parents = build_index(qdrant_path=a.path, model=a.model)
    reranker = None if a.no_rerank else get_reranker(a.reranker)
    retr = HybridRetriever(client, emb, children, parents, reranker)

    rewriter = None
    if a.rewrite:
        from src.llm import get_llm
        from src.rag.rewrite import QueryRewriter
        rewriter = QueryRewriter(get_llm())

    ranks, per_policy, misses = evaluate(retr, questions, mode, rewriter=rewriter)
    total = _metrics(ranks)
    n = total["n"]

    sep = "=" * 62
    print(sep)
    print("HELD-OUT RETRIEVAL EVALUATION")
    print(f"  questions : {a.questions}")
    print(f"  sha256    : {sha}")
    print(f"  n         : {n}  (small sample – treat counts as primary)")
    print(f"  pipeline  : {mode}")
    print(f"  model     : {a.model}")
    print(sep)

    # Per-policy table
    print(f"\n{'Per-policy results':}")
    hdr = f"  {'policy':<36} {'n':>3}  {'@1':>4}  {'@3':>4}  {'@5':>4}   mrr"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for pol, pol_ranks in sorted(per_policy.items()):
        m = _metrics(pol_ranks)
        pn = m["n"]
        print(f"  {pol:<36} {pn:>3}  {m['recall@1']:>3}/{pn}  {m['recall@3']:>3}/{pn}  {m['recall@5']:>3}/{pn}   {m['mrr']:.3f}")
    print("  " + "─" * (len(hdr) - 2))
    t = total
    print(f"  {'TOTAL':<36} {n:>3}  {t['recall@1']:>3}/{n}  {t['recall@3']:>3}/{n}  {t['recall@5']:>3}/{n}   {t['mrr']:.3f}")

    # Raw counts + percentages
    print(f"\nRaw counts   recall@1 {t['recall@1']}/{n}   recall@3 {t['recall@3']}/{n}   recall@5 {t['recall@5']}/{n}")
    print(f"Percentages  recall@1 {100*t['recall@1']/n:.1f}%   recall@3 {100*t['recall@3']/n:.1f}%   recall@5 {100*t['recall@5']/n:.1f}%   mrr {t['mrr']:.3f}")

    # Generalisation note
    tuned_r3 = 0.929
    actual_r3_pct = 100 * t["recall@3"] / n
    gap = tuned_r3 * 100 - actual_r3_pct
    print(f"\nNote: 28-question tuned benchmark recall@3 = {tuned_r3*100:.1f}%")
    if gap > 0:
        print(f"      Held-out generalisation gap = {gap:.1f} pp  (expected; held-out questions were never used to tune anything)")
    else:
        print(f"      Held-out recall@3 matches or exceeds the tuned benchmark.")

    # Misses
    print(f"\nMisses for {mode} (rank > 3 or not found):")
    if misses:
        for qid, q, gold, got, rank in misses:
            print(f"  [{qid}] rank={rank}  gold={gold}")
            print(f"         got_top3={got}")
            print(f"         {q}")
    else:
        print("  (none — all questions retrieved in top 3)")


if __name__ == "__main__":
    main()
