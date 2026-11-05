"""Cross-encoder reranker. 'hash' is a dependency-free stand-in for tests."""
from __future__ import annotations

import re


class HashReranker:
    def score(self, query: str, passages: list[str]) -> list[float]:
        q = set(re.findall(r"[a-z0-9]+", query.lower()))
        out = []
        for p in passages:
            w = set(re.findall(r"[a-z0-9]+", p.lower()))
            out.append(len(q & w) / (len(q | w) or 1))
        return out


class CEReranker:
    def __init__(self, name: str):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(name)

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(x) for x in self.model.predict([(query, p) for p in passages], show_progress_bar=False)]


def get_reranker(name: str):
    return HashReranker() if name == "hash" else CEReranker(name)