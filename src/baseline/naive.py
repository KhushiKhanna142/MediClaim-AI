"""The 'before' system: naive OCR, naive retrieval, one LLM call that does everything including the arithmetic.

It exists to be beaten. Deliberately missing: structured extraction, rule checks, the calculator, reranking,
query rewriting, verification and human review. Policy id is passed in (the real system will infer it from the form).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.baseline.ocr import read_claim_docs

DECISIONS = ("approve", "partial", "reject", "needs_review")
DOC_ORDER = ["claim_form", "policy_schedule", "discharge_summary", "hospital_bill", "id_proof", "lab_report", "prescription"]

SYSTEM = """You are a health insurance claim adjudicator for Indian reimbursement claims.
You are given the text of the claim documents and extracts from the policy wording. Decide the claim.
Reply with one JSON object and nothing else, with these keys:
decision: one of approve, partial, reject, needs_review (use needs_review when required documents are missing or figures do not reconcile)
payable_amount: number in rupees the insurer should pay (0 if rejected)
cited_clause_ids: list of clause ids from the policy extracts that support your decision
reasoning: two or three sentences"""


def build_claim_text(docs: dict[str, dict]) -> str:
    names = [n for n in DOC_ORDER if n in docs] + [n for n in docs if n not in DOC_ORDER]
    return "\n\n".join(f"=== {n.upper()} ===\n{docs[n]['text'].strip()}" for n in names)


def build_query(docs: dict[str, dict], max_chars: int = 500) -> str:
    """Naive query: the start of the discharge summary and claim form text."""
    src = (docs.get("discharge_summary", {}).get("text", "") + " " + docs.get("claim_form", {}).get("text", ""))
    return re.sub(r"\s+", " ", src).strip()[:max_chars]


def build_prompt(claim_text: str, hits: list[dict]) -> str:
    ctx = "\n\n".join(f"[clause {h['clause_id']}] {h.get('text', '')[:1200]}" for h in hits)
    return f"CLAIM DOCUMENTS\n{claim_text}\n\nPOLICY EXTRACTS\n{ctx}\n\nDecide the claim."


def parse_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    body = m.group(0) if m else ""
    # models sometimes write numbers as 118,400, which is not valid JSON
    body = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", body)   # 118,400 -> 118400; leaves the comma between JSON fields alone
    try:
        d = json.loads(body) if body else {}
    except json.JSONDecodeError:
        d = {}
    dec = str(d.get("decision", "")).strip().lower().replace(" ", "_")
    try:
        pay = float(str(d.get("payable_amount", "")).replace(",", ""))
    except ValueError:
        pay = None
    cites = [str(c).strip() for c in d.get("cited_clause_ids", []) if str(c).strip()] if isinstance(d.get("cited_clause_ids"), list) else []
    return {"decision": dec if dec in DECISIONS else None, "payable_amount": pay,
            "cited_clause_ids": cites, "reasoning": str(d.get("reasoning", ""))}


class NaiveBaseline:
    name = "naive_baseline"

    def __init__(self, retriever, llm, k: int = 5, mode: str = "dense"):
        self.retriever, self.llm, self.k, self.mode = retriever, llm, k, mode

    def predict(self, claim_dir: Path, policy_id: str) -> dict:
        docs = read_claim_docs(claim_dir)
        hits = self.retriever.search(build_query(docs), k=self.k, policy_ids=[policy_id], mode=self.mode)
        reply = self.llm.complete(SYSTEM, build_prompt(build_claim_text(docs), hits), max_tokens=600)
        out = parse_reply(reply)
        out["raw_reply"] = reply[:1500]
        if out["decision"] is None:
            out["error"] = "no valid decision in model reply (empty reply or not JSON)"
        out["retrieved_clause_ids"] = [h["clause_id"] for h in hits]
        return out