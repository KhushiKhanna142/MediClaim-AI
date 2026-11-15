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
non_payable_clause: clause id or annexure that LISTS the expenses that are not payable (non-medical items, consumables), or null. Any clause saying the insurer will cover or pay for such items (an add-on benefit, rider, or optional cover, whatever it is called) is a coverage benefit and not the exclusion list: never cite it here. A list placed after the last clause is often indexed under that clause's id; cite the id it appears under
sum_insured_clause: clause id defining sum insured or limiting payment to it, or null
coverage_clause: clause id of the main in-patient hospitalization benefit, i.e. what is paid for a covered hospital stay (room, nursing, surgeon, medicines), or null. Not post-hospitalization, pre-hospitalization, day-care or add-on benefits
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

COVERAGE_QUERIES = (
    "the Company shall indemnify we will pay medical expenses incurred hospitalization inpatient treatment covered benefit",
    "Hospitalization Expenses: the Company shall indemnify medical expenses incurred during in-patient hospitalization such as room rent, nursing, surgeon fees and medicines",
)


def gather(retriever, c: ExtractedClaim, policy_id: str) -> dict[str, list[dict]]:
    out = {}
    for topic, q in TOPICS.items():
        if topic == "room_modification" and not c.room_type_modification:
            continue
        if topic == "coverage":
            seen = set()
            merged = []
            for cq in COVERAGE_QUERIES:
                for h in retriever.search(cq, k=K_PER_TOPIC, policy_ids=[policy_id], mode=TOPIC_MODE.get(topic, "hybrid_rerank")):
                    if h["clause_id"] not in seen:
                        seen.add(h["clause_id"])
                        merged.append(h)
            out[topic] = merged
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


LONG_TOPICS = {"initial_waiting", "specified", "pre_existing", "diagnosis_lookup", "non_payable"}   # lists of conditions can sit late in a clause
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


# Targeted retry: when the verifier reports that an applied rule has no supporting clause, ask a focused question about that one
# clause field instead of re-running the whole reading (which would repeat the same omission). Only citations are filled in;
# no judgement (specified / pre-existing / waiting days / room co-pay %) is ever changed by a refine pass.
REFINE_K = 6
REFINE_FIELDS = {
    "non_payable_clause": ("non_payable", "the list of expenses that are not payable, or the non-medical items that are excluded"),
    "sum_insured_clause": ("sum_insured", "the definition of sum insured or the rule limiting the amount payable to it"),
    "room_cap_clause": ("room", "the room rent limit or the proportionate deduction of other charges"),
    "copay_clause": ("copay", "the co-payment the insured must bear"),
    "coverage_clause": ("coverage", "what in-patient hospitalization expenses are covered"),
    "room_mod_clause": ("room_modification", "the co-payment for a room type modification"),
    "initial_wait_clause": ("initial_waiting", "the initial waiting period"),
    "spec_clause": ("specified", "the waiting period for specified diseases and procedures"),
    "ped_clause": ("pre_existing", "the waiting period for pre-existing diseases"),
    "ped_def_clause": ("pre_existing", "the definition of pre-existing disease"),
}
REFINE_QUERIES = {"copay": "co-payment percentage of the admissible claim to be borne by the insured"}
REFINE_SYSTEM = """You help cite an Indian health insurance policy wording. You get a description of one rule and candidate clauses.
Reply with one JSON object and nothing else: {"clause": <id or null>}.
Choose the clause that itself states the rule. Use null if none of the candidates states it. Copy the id exactly as it appears inside the
square brackets of the candidates, written WITHOUT the brackets. Do not guess an id that is not shown."""


def allowed_ids(hits: list[dict]) -> set[str]:
    out = set()
    for h in hits:
        cid = base_clause_id(h["clause_id"])
        out |= {cid, cid.split("/")[0]}
    return out


def parse_single_clause(reply: str, hits: list[dict]) -> str | None:
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        v = json.loads(m.group(0)).get("clause") if m else None
    except ValueError:
        return None
    cid = base_clause_id(clean_id(v)) if v not in (None, "", []) else ""
    return cid if cid and cid.lower() != "null" and cid in allowed_ids(hits) else None


class PolicyReader:
    def __init__(self, retriever, llm):
        self.retriever, self.llm = retriever, llm

    def refine(self, c: ExtractedClaim, policy_id: str, fields: list[str], previous: Findings) -> tuple[Findings, dict]:
        """Fill the named clause fields of `previous` that are still empty, one focused call per field."""
        data, retrieved, dropped, filled = previous.model_dump(), {}, [], []
        for f in fields:
            if f not in REFINE_FIELDS or data.get(f):
                continue
            topic, what = REFINE_FIELDS[f]
            if topic == "coverage":
                seen = set()
                hits = []
                for cq in COVERAGE_QUERIES:
                    for h in self.retriever.search(cq, k=3, policy_ids=[policy_id], mode="hybrid_rerank"):
                        if h["clause_id"] not in seen:
                            seen.add(h["clause_id"])
                            hits.append(h)
            else:
                query = (TOPICS.get(topic) or REFINE_QUERIES[topic]).format(dx=c.diagnosis)
                hits = self.retriever.search(query, k=REFINE_K, policy_ids=[policy_id], mode="hybrid_rerank")
            retrieved[f"refine:{f}"] = [h["clause_id"] for h in hits]
            body = "\n".join(f"[{h['clause_id']}] {passage(h, LONG_LIMIT)}" for h in hits)
            cid = parse_single_clause(self.llm.complete(REFINE_SYSTEM, f"RULE: {what}\n\nCANDIDATES\n{body}", max_tokens=200), hits)
            if cid:
                data[f] = cid
                filled.append(f"{f}={cid}")
            else:
                dropped.append(f"{f}=none_found")
        return Findings.model_validate(data), {"retrieved": retrieved, "dropped_citations": dropped, "refined": filled}

    def read(self, c: ExtractedClaim, policy_id: str, refine: list[str] | None = None,
             previous: Findings | None = None) -> tuple[Findings, dict]:
        if refine and previous is not None:
            return self.refine(c, policy_id, refine, previous)
        evidence = gather(self.retriever, c, policy_id)
        reply = self.llm.complete(SYSTEM, build_prompt(c, evidence), max_tokens=1500)
        findings, dropped = parse_findings(reply, evidence)
        trace = {"retrieved": {t: [h["clause_id"] for h in hs] for t, hs in evidence.items()}, "dropped_citations": dropped}
        return findings, trace