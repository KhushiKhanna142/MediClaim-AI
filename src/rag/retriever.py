"""Hybrid retriever: dense (Qdrant) + BM25, fused with reciprocal rank fusion, expanded to parent clauses.

Always filter by policy_id / insurer (never mix one insurer's rules into another's) and by claim date.
"""
from __future__ import annotations

import re
from datetime import date

import numpy as np
from qdrant_client.models import FieldCondition, Filter, MatchAny
from rank_bm25 import BM25Okapi

from src.rag.index import COLLECTION, embed_text

RRF_K = 60
POOL = 40
RERANK_POOL = 20


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", text.lower())


def _active(c: dict, as_of: date | None) -> bool:
    if as_of is None:
        return True
    lo, hi = c.get("effective_from"), c.get("effective_to")
    return (not lo or date.fromisoformat(lo) <= as_of) and (not hi or as_of <= date.fromisoformat(hi))


def base_clause_id(chunk_id_or_clause: str) -> str:
    return re.sub(r"(#\d+)?(~p\d+)?$", "", chunk_id_or_clause)


class HybridRetriever:
    def __init__(self, client, embedder, children: list[dict], parents: dict[str, dict], reranker=None):
        self.client, self.emb, self.children, self.parents = client, embedder, children, parents
        self.reranker = reranker
        self.bm25 = BM25Okapi([tokenize(embed_text(c)) for c in children])

    def _allowed(self, policy_ids, insurers, as_of) -> np.ndarray:
        return np.array([
            (not policy_ids or c["policy_id"] in policy_ids) and (not insurers or c["insurer"] in insurers)
            and _active(c, as_of) for c in self.children])

    def _dense(self, query: str, allowed: np.ndarray, policy_ids) -> list[int]:
        qv = self.emb.encode([self.emb.query_prefix + query])[0].tolist()
        flt = Filter(must=[FieldCondition(key="policy_id", match=MatchAny(any=list(policy_ids)))]) if policy_ids else None
        res = self.client.query_points(COLLECTION, query=qv, limit=POOL * 3, query_filter=flt).points
        return [p.payload["idx"] for p in res if allowed[p.payload["idx"]]][:POOL]

    def _bm25(self, query: str, allowed: np.ndarray) -> list[int]:
        scores = np.array(self.bm25.get_scores(tokenize(query)))
        scores[~allowed] = -1.0
        order = np.argsort(-scores)[:POOL]
        return [int(i) for i in order if scores[i] > 0]

    def search(self, query: str, k: int = 5, policy_ids=None, insurers=None, as_of: date | None = None,
               mode: str = "hybrid", extra_queries: list[str] | None = None) -> list[dict]:
        """extra_queries: rewrites of the query. Candidates from all queries are fused; the reranker scores each
        candidate against every query and keeps the best score."""
        allowed = self._allowed(set(policy_ids or []), set(insurers or []), as_of)
        queries = [query] + [q for q in (extra_queries or []) if q and q != query]
        fused: dict[int, float] = {}
        for q in queries:
            lists = []
            if mode in ("dense", "hybrid", "hybrid_rerank"):
                lists.append(self._dense(q, allowed, policy_ids))
            if mode in ("bm25", "hybrid", "hybrid_rerank"):
                lists.append(self._bm25(q, allowed))
            for lst in lists:
                for rank, idx in enumerate(lst, 1):
                    fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        if mode == "hybrid_rerank":
            if self.reranker is None:
                raise ValueError("hybrid_rerank needs a reranker")
            pool = ranked[:RERANK_POOL]
            texts = [embed_text(self.children[i]) for i, _ in pool]
            per_query = [self.reranker.score(q, texts) for q in queries]
            best = [max(col) for col in zip(*per_query)]
            ranked = sorted(((i, sc) for (i, _), sc in zip(pool, best)), key=lambda x: -x[1])
        results, seen = [], set()
        for idx, score in ranked:
            c = self.children[idx]
            if c["parent_id"] in seen:
                continue
            seen.add(c["parent_id"])
            par = self.parents[c["parent_id"]]
            results.append({"policy_id": c["policy_id"], "clause_id": c["clause_id"], "parent_id": c["parent_id"],
                            "section": c["section"], "page_start": par["page_start"], "page_end": par["page_end"],
                            "score": round(float(score), 5), "child_text": c["text"], "text": par["text"]})
            if len(results) == k:
                break
        return results