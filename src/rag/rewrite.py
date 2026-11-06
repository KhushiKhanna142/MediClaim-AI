"""Query rewriting: turn a claim-style question into short queries phrased like policy wording.

The original question is always kept as a query too, so a bad rewrite can only add candidates, never remove the original.
Rewrites are cached on disk so evaluation runs are repeatable and cost nothing the second time.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SYSTEM = (
    "You help retrieve clauses from Indian health insurance policy wordings. Rewrite the claim question into 2 or 3 short "
    "search queries written the way policy wordings phrase things: use policy terms such as waiting period, exclusion, "
    "pre-existing disease, sub-limit, co-payment, room rent, sum insured, optional benefit. Express time periods the way "
    "policies do (for example 'within 30 days of policy commencement', 'after 24 months of continuous coverage'). Do not "
    "invent numbers, amounts or insurer names. Reply with only a JSON array of strings."
)


def parse_rewrites(raw: str, max_n: int = 3) -> list[str]:
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = [a.strip() for a in arr if isinstance(a, str) and a.strip()]
    return out[:max_n]


class QueryRewriter:
    def __init__(self, llm, cache_path: str | None = "data/golden_set/rewrite_cache.json"):
        self.llm = llm
        self.path = Path(cache_path) if cache_path else None
        self.cache: dict[str, list[str]] = {}
        if self.path and self.path.exists():
            self.cache = json.loads(self.path.read_text())

    def __call__(self, question: str) -> list[str]:
        key = hashlib.sha1(question.encode()).hexdigest()
        if key not in self.cache:
            self.cache[key] = parse_rewrites(self.llm.complete(SYSTEM, question))
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.cache, indent=1))
        return self.cache[key]