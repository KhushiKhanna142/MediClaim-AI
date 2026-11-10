"""validate -> read policy -> decide. Validation failures stop the claim before any policy reading."""
from __future__ import annotations

from pathlib import Path

from src.adjudication.engine import decide
from src.adjudication.reader import PolicyReader
from src.extraction.schemas import ExtractedClaim
from src.validation.checks import validate


class Adjudicator:
    def __init__(self, retriever, llm):
        self.reader = PolicyReader(retriever, llm)

    def run(self, c: ExtractedClaim, policy_id: str, docs_present: list[str]) -> dict:
        report = validate(c, docs_present)
        if report.needs_review:
            return {"decision": "needs_review", "payable_amount": None, "deductions": [], "cited_clause_ids": [],
                    "flags": report.flags, "reasons": report.details, "retrieved_clause_ids": []}
        findings, trace = self.reader.read(c, policy_id)
        out = decide(c, findings)
        out["flags"], out["warnings"] = [], report.warnings
        out["findings"] = findings.model_dump()
        out["retrieved_clause_ids"] = sorted({cid for ids in trace["retrieved"].values() for cid in ids})
        out["dropped_citations"] = trace["dropped_citations"]
        return out