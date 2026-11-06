"""Retrieval-only evaluation: recall@k and MRR at clause level, for dense / bm25 / hybrid.

Questions file (JSONL): {"id", "question", "policy_id", "gold_clause_ids": [...]}
A hit = a retrieved parent whose clause_id (ignoring ~pN / #N suffixes) is in gold_clause_ids.

CLI (from repo root):  python -m eval.retrieval_eval [--questions data/golden_set/retrieval_questions_seed.jsonl]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.rag.index import DEFAULT_MODEL, build_index
from src.rag.reranker import get_reranker
from src.rag.retriever import HybridRetriever, base_clause_id

KS = (1, 3, 5)


def evaluate(retr: HybridRetriever, questions: list[dict], mode: str, k: int = 10, rewriter=None):
    ranks, misses = [], []
    for q in questions:
        base_mode = mode[:-3] if mode.endswith("_rw") else mode
        extra = rewriter(q["question"]) if mode.endswith("_rw") and rewriter else None
        res = retr.search(q["question"], k=k, policy_ids=[q["policy_id"]] if q.get("policy_id") else None,
                          mode=base_mode, extra_queries=extra)
        gold = set(q["gold_clause_ids"])
        rank = next((i for i, r in enumerate(res, 1) if base_clause_id(r["clause_id"]) in gold), None)
        ranks.append(rank)
        if rank is None or rank > 3:
            misses.append((q["id"], q["question"], sorted(gold), [r["clause_id"] for r in res[:3]], rank))
    n = len(questions)
    out = {f"recall@{kk}": sum(1 for r in ranks if r and r <= kk) / n for kk in KS}
    out["mrr"] = sum(1 / r for r in ranks if r) / n
    return out, misses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="data/golden_set/retrieval_questions_seed.jsonl")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--path", default="data/qdrant")
    ap.add_argument("--reranker", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--rewrite", action="store_true", help="also run query-rewriting modes (needs an LLM API key)")
    a = ap.parse_args()
    questions = [json.loads(l) for l in Path(a.questions).read_text().splitlines() if l.strip()]
    client, emb, children, parents = build_index(qdrant_path=a.path, model=a.model)
    retr = HybridRetriever(client, emb, children, parents, None if a.no_rerank else get_reranker(a.reranker))
    print(f"{len(questions)} questions, model={a.model}\n")
    print(f"{'mode':13} " + " ".join(f"recall@{k}" for k in KS) + "   mrr")
    rewriter = None
    if a.rewrite:
        from src.llm import get_llm
        from src.rag.rewrite import QueryRewriter
        rewriter = QueryRewriter(get_llm())
    modes = ["dense", "bm25", "hybrid"] + ([] if a.no_rerank else ["hybrid_rerank"]) + \
            (["hybrid_rw"] + ([] if a.no_rerank else ["hybrid_rerank_rw"]) if a.rewrite else [])
    all_misses = {}
    for mode in modes:
        m, misses = evaluate(retr, questions, mode, rewriter=rewriter)
        all_misses[mode] = misses
        print(f"{mode:13} " + " ".join(f"{m[f'recall@{k}']:8.2f}" for k in KS) + f"   {m['mrr']:.3f}")
    best = modes[-1]
    print(f"\nMisses for {best} (rank > 3 or not found):")
    for qid, q, gold, got, rank in all_misses[best]:
        print(f"  [{qid}] rank={rank} gold={gold} got_top3={got}\n      {q}")


if __name__ == "__main__":
    main()