"""Policy reading: retrieve clauses per topic, then one LLM call that makes the policy-specific judgements.

The model may only cite clause ids that were actually retrieved for this claim; any other id is dropped and recorded.
It is told nothing about what the answer should be, and it never sees the rule sets used to generate the ground truth.
"""
from __future__ import annotations

import json
import re

from src.adjudication.findings import CLAUSE_FIELDS, Findings
from src.extraction.schemas import ExtractedClaim
from src.rag.retriever import base_clause_id
from src.security.pii import redact_pii

K_PER_TOPIC = 3

SYSTEM = """You read an Indian health insurance policy wording to answer specific questions about one claim.
You get facts about the claim and candidate clauses grouped by topic. Use ONLY the candidate clauses.
Reply with one JSON object and nothing else:
initial_waiting_days: number of days of the initial waiting period for illness in this policy, or null if the clauses do not state one
initial_wait_clause: clause id that states it, or null
is_specified: true if the diagnosis or procedure appears in this policy's list of specified diseases/procedures with a waiting period
spec_clause: clause id of that list or its waiting period rule, or null
is_pre_existing: true if the claimant's history shows a condition that meets this policy's definition of pre-existing disease and relates to the diagnosis
ped_clause: clause id of the pre-existing disease waiting period rule, or null
ped_def_clause: clause id defining pre-existing disease, or null
room_cap_clause: clause id for the room rent limit or proportionate deduction, or null
room_modification_copay_pct: if the claim form's eligible room and claimed room differ and a room type modification clause gives a co-payment for that pair, the percentage; otherwise null
room_mod_clause: clause id of that room type modification clause, or null
copay_clause: clause id for co-payment, or null
non_payable_clause: clause id for non-payable or non-medical expenses, or null
sum_insured_clause: clause id defining sum insured or limiting payment to it, or null
coverage_clause: clause id stating what hospitalization expenses are covered, or null
reasoning: two sentences
CANDIDATES for diagnosis_lookup are passages that mention the diagnosis itself; the list of specified conditions may be among them even if it is not in the clause that refers to it.
Clause ids must be copied exactly as they appear inside the square brackets of the candidates, but written WITHOUT the brackets (for example Section C, not [Section C]). Do not guess an id that is not shown."""

TOPICS = {
    "initial_waiting": "initial waiting period first 30 days from policy start illness not covered accident exempt",
    "specified": "waiting period specified diseases and procedures list covered after months {dx}",
    "pre_existing": "pre-existing disease definition and waiting period before coverage",
    "room": "room rent limit per day proportionate deduction of other charges",
    "room_modification": "room type modification co-payment shared room single room deluxe room",
    "non_payable": "non-medical expenses not payable items consumables list",
    "coverage": "the Company shall indemnify we will pay medical expenses incurred hospitalization inpatient treatment covered benefit",
    "sum_insured": "sum insured definition maximum liability limit",
    "diagnosis_lookup": "{dx}",
}
TOPIC_MODE = {"diagnosis_lookup": "hybrid"}   # keyword-leaning: a rare word such as the procedure name finds the list that contains it


def gather(retriever, c: ExtractedClaim, policy_id: str) -> dict[str, list[dict]]:
    out = {}
    for topic, q in TOPICS.items():
        if topic == "room_modification" and not c.room_type_modification:
            continue
        query = q.format(dx=c.diagnosis)
        k = 4 if topic == "diagnosis_lookup" else K_PER_TOPIC
        out[topic] = retriever.search(query, k=k, policy_ids=[policy_id], mode=TOPIC_MODE.get(topic, "hybrid_rerank"))
    return out


def build_prompt(c: ExtractedClaim, evidence: dict[str, list[dict]]) -> str:
    facts = [f"diagnosis: {redact_pii(c.diagnosis)}", f"cause: {c.cause}",
             f"history stated in discharge summary: {redact_pii(c.known_history) if c.known_history else 'none stated'}",
             f"history onset date: {c.history_onset_date or 'not stated'}", f"admission date: {c.admission_date}",
             f"policy start date: {c.policy_start}", f"eligible room (from schedule): {c.eligible_room}",
             f"room claimed: {c.room_category_claimed}", f"room type modification opted: {c.room_type_modification}"]
    parts = ["CLAIM FACTS\n" + "\n".join(facts)]
    for topic, hits in evidence.items():
        body = "\n".join(f"[{h['clause_id']}] {passage(h, LONG_LIMIT if topic in LONG_TOPICS else 1100)}" for h in hits)
        parts.append(f"CANDIDATES for {topic}\n{body}")
    return "\n\n".join(parts)


def clean_id(v) -> str:
    """Models often echo the bracket and even the clause text after it. Keep only the id."""
    s = str(v[0] if isinstance(v, list) and v else v).strip()
    m = re.match(r"^\[([^\]]+)\]", s)
    return (m.group(1) if m else s).strip().strip("[]'\" ")


LONG_TOPICS = {"initial_waiting", "specified", "pre_existing", "diagnosis_lookup"}   # lists of conditions can sit late in a clause
LONG_LIMIT = 3000


def passage(h: dict, limit: int = 1100) -> str:
    """The whole clause when it fits the limit; otherwise the clause start plus the child passage that matched,
    so a long list is never cut before the matching item."""
    parent, child = h["text"], h.get("child_text") or ""
    if len(parent) <= limit:
        return parent
    if not child or child[:200] in parent[:limit]:
        return parent[:limit]
    return parent[:450] + "\n...\n" + child[:900]


def parse_findings(reply: str, evidence: dict[str, list[dict]]) -> tuple[Findings, list[str]]:
    """Validates the reply and drops any cited clause id that was not among the retrieved candidates."""
    m = re.search(r"\{.*\}", reply, re.S)
    raw = json.loads(m.group(0)) if m else {}
    allowed = set()
    for hits in evidence.values():
        for h in hits:
            cid = base_clause_id(h["clause_id"])
            allowed |= {cid, cid.split("/")[0]}   # a sub-item such as 2.13/1 also makes its parent clause 2.13 citable
    dropped = []
    for f in CLAUSE_FIELDS:
        v = raw.get(f)
        cid = base_clause_id(clean_id(v)) if v not in (None, "", []) else ""
        if not cid or cid.lower() == "null":
            raw[f] = None
        elif cid not in allowed:
            dropped.append(f"{f}={cid}")
            raw[f] = None
        else:
            raw[f] = cid
    return Findings.model_validate({k: v for k, v in raw.items() if k in Findings.model_fields}), dropped


class PolicyReader:
    def __init__(self, retriever, llm):
        self.retriever, self.llm = retriever, llm

    def read(self, c: ExtractedClaim, policy_id: str) -> tuple[Findings, dict]:
        evidence = gather(self.retriever, c, policy_id)
        reply = self.llm.complete(SYSTEM, build_prompt(c, evidence), max_tokens=1500)
        findings, dropped = parse_findings(reply, evidence)
        trace = {"retrieved": {t: [h["clause_id"] for h in hs] for t, hs in evidence.items()}, "dropped_citations": dropped}
        return findings, trace