"""LangGraph workflow for claim adjudication.

  extract -> security_scan -> validate -> read_policy -> decide -> verify -> route -> (human_review) -> finalise
                                 |                          ^         |
                                 | validation failed        +---------+  verifier failed, retry capped
                                 +-----------------------------------> route

Design rules:
  * The LLM never does arithmetic: `decide` is the deterministic engine, the verifier recomputes independently.
  * `decision` is the system's recommendation and is never overwritten. A human reviewer's action lands in `human_action`
    and `final`, so the override rate (human differs from system) can be measured.
  * Every path that cannot be trusted ends in `human_review`, which pauses via interrupt() until someone resumes it.
  * Components are injected, so the graph runs in tests without an LLM, vector store or OCR.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.extraction.schemas import ExtractedClaim
from src.graph.state import ClaimState
from src.validation.checks import docs_in_dir, validate

INJECTION_PATTERNS = [r"ignore (all |any )?(previous|prior|above)", r"approve (this|the) claim", r"system prompt",
                      r"you are (now )?an? ", r"disregard (the )?(policy|rules|instructions)", r"pay (the )?(full|entire) (amount|claim)",
                      r"override"]
HUMAN_ACTIONS = ("approve", "edit", "reject")


@dataclass
class GraphConfig:
    max_verify_retries: int = 2                    # extra policy-reading attempts after the first, when verification fails
    min_verifier_confidence: float = 0.7
    high_amount_threshold: Optional[float] = None  # payable above this goes to a human; None disables the rule
    review_all_rejects: bool = False               # set True in production: never auto-deny a claim


def validate_human_action(action: Optional[dict], ai_status: Optional[str]) -> None:
    """Raises ValueError for an action that cannot be applied. Called by resume_claim BEFORE the graph is resumed: a value that
    fails inside the paused node would be replayed on every retry and leave the claim stuck."""
    kind = (action or {}).get("action")
    if kind not in HUMAN_ACTIONS:
        raise ValueError(f"action must be one of {HUMAN_ACTIONS}")
    if kind == "approve" and ai_status not in ("approve", "partial", "reject"):
        raise ValueError("nothing to approve: the system made no recommendation; use 'edit' or 'reject'")
    if kind == "edit":
        if action.get("status") not in ("approve", "partial", "reject"):
            raise ValueError("edit needs status: approve, partial or reject")
        if action["status"] != "reject" and not (action.get("payable_amount") or 0) > 0:
            raise ValueError("edit to approve/partial needs a positive payable_amount")


def default_security_scan(extracted: dict) -> list[str]:
    """Flag instruction-like text in free-text fields. Flag and escalate; never follow it."""
    fields = [str(extracted.get(k) or "") for k in ("diagnosis", "known_history", "patient_name", "hospital")]
    fields += [str(i.get("description", "")) for i in extracted.get("items") or []]
    flags = []
    for text in fields:
        for pat in INJECTION_PATTERNS:
            if re.search(pat, text, re.I):
                flags.append(f"injection_pattern:{pat}")
    return sorted(set(flags))


def _event(node: str, **detail) -> dict:
    return {"node": node, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "detail": detail}


def build_graph(*, reader=None, verifier=None, extractor=None, decide_fn: Optional[Callable] = None, findings_cls=None,
                security_scan: Callable[[dict], list[str]] = default_security_scan, config: Optional[GraphConfig] = None,
                checkpointer=None):
    """reader: PolicyReader (read(claim, policy_id) -> (findings, trace)). verifier: Verifier. extractor: Extractor, only needed
    when a claim is submitted as a directory. decide_fn defaults to the deterministic engine."""
    cfg = config or GraphConfig()
    if decide_fn is None:
        from src.adjudication.engine import decide as decide_fn  # noqa: PLC0415 - heavy imports only when really used
    if findings_cls is None:
        from src.adjudication.findings import Findings as findings_cls  # noqa: PLC0415

    def claim_of(state) -> ExtractedClaim:
        return ExtractedClaim.model_validate(state["extracted"])

    # ------------------------------------------------------------------ nodes
    def extract(state: ClaimState) -> dict:
        out: dict[str, Any] = {}
        if state.get("claim_dir") and not state.get("docs_present"):
            out["docs_present"] = docs_in_dir(Path(state["claim_dir"]))
        if state.get("extracted"):
            return {**out, "audit": [_event("extract", skipped="pre-extracted input")]}
        try:
            claim = extractor.extract_dir(Path(state["claim_dir"]))
            return {**out, "extracted": claim.model_dump(mode="json"), "audit": [_event("extract", ok=True, vision_filled=claim.vision_filled)]}
        except Exception as exc:  # noqa: BLE001
            return {**out, "extraction_error": repr(exc)[:300], "audit": [_event("extract", ok=False, error=type(exc).__name__)]}

    def security(state: ClaimState) -> dict:
        flags = security_scan(state["extracted"])
        return {"security_flags": flags, "audit": [_event("security_scan", flags=flags)]}

    def validate_node(state: ClaimState) -> dict:
        report = validate(claim_of(state), state.get("docs_present") or [])
        out: dict[str, Any] = {"validation_flags": report.flags, "validation_warnings": report.warnings,
                               "validation_details": report.details,
                               "audit": [_event("validate", flags=report.flags, warnings=report.warnings)]}
        if report.needs_review:
            out["decision"] = {"decision": "needs_review", "payable_amount": None, "deductions": [], "cited_clause_ids": [],
                               "flags": report.flags, "reasons": report.details, "retrieved_clause_ids": []}
        return out

    def read_policy(state: ClaimState) -> dict:
        retries = dict(state.get("retries") or {})
        retries["read_policy"] = retries.get("read_policy", 0) + 1
        findings, trace = reader.read(claim_of(state), state["policy_id"])
        ids = sorted({cid for v in trace["retrieved"].values() for cid in v})
        return {"findings": findings.model_dump(), "retrieved_clause_ids": ids, "dropped_citations": trace.get("dropped_citations", []),
                "retries": retries, "audit": [_event("read_policy", attempt=retries["read_policy"], n_clauses=len(ids))]}

    def decide(state: ClaimState) -> dict:
        out = decide_fn(claim_of(state), findings_cls.model_validate(state["findings"]))
        out.update(flags=[], warnings=state.get("validation_warnings", []), findings=state["findings"],
                   retrieved_clause_ids=state["retrieved_clause_ids"], dropped_citations=state.get("dropped_citations", []))
        return {"decision": out, "audit": [_event("decide", status=out["decision"], payable=out["payable_amount"])]}

    def verify(state: ClaimState) -> dict:
        res = verifier.verify(claim_of(state), state["findings"], state["decision"], state["retrieved_clause_ids"])
        return {"verifier": res.to_dict(), "verifier_feedback": None if res.passed else res.feedback(),
                "audit": [_event("verify", passed=res.passed, confidence=res.confidence, issues=res.issues, concerns=res.concerns)]}

    def route(state: ClaimState) -> dict:
        why: list[str] = []
        dec = state.get("decision") or {}
        ver = state.get("verifier")
        if state.get("extraction_error"):
            why.append("extraction_failed")
        if state.get("security_flags"):
            why.append("security_flag")
        if dec.get("decision") == "needs_review" or state.get("validation_flags"):
            why += [f"validation:{f}" for f in state.get("validation_flags", [])] or ["needs_review"]
        if ver is not None:
            if not ver["passed"]:
                why.append("verifier_failed")
            elif ver["confidence"] < cfg.min_verifier_confidence:
                why.append("low_confidence")
        if cfg.high_amount_threshold is not None and (dec.get("payable_amount") or 0) > cfg.high_amount_threshold:
            why.append("high_amount")
        if cfg.review_all_rejects and dec.get("decision") == "reject":
            why.append("reject_requires_review")
        why = list(dict.fromkeys(why))
        return {"needs_human": bool(why), "escalation_reasons": why, "audit": [_event("route", needs_human=bool(why), reasons=why)]}

    def human_review(state: ClaimState) -> dict:
        packet = {"claim_id": state.get("claim_id"), "escalation_reasons": state.get("escalation_reasons"),
                  "recommendation": state.get("decision"), "verifier": state.get("verifier"),
                  "validation_details": state.get("validation_details"), "extraction_error": state.get("extraction_error"),
                  "security_flags": state.get("security_flags"), "retrieved_clause_ids": state.get("retrieved_clause_ids"),
                  "extracted": state.get("extracted"), "audit": state.get("audit")}
        action = interrupt(packet)
        validate_human_action(action, (state.get("decision") or {}).get("decision"))   # defence in depth; resume_claim checks first
        kind = action["action"]
        return {"human_action": {**action, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                "audit": [_event("human_review", action=kind, reviewer=action.get("reviewer"))]}

    def finalise(state: ClaimState) -> dict:
        ai = state.get("decision") or {}
        human = state.get("human_action")
        if human is None:
            final = {"status": ai["decision"], "payable_amount": ai["payable_amount"], "source": "auto",
                     "cited_clause_ids": ai.get("cited_clause_ids", []), "reasons": ai.get("reasons", []), "override": False}
        else:
            kind = human["action"]
            if kind == "approve":
                status, payable = ai["decision"], ai["payable_amount"]
            elif kind == "reject":
                status, payable = "reject", 0.0
            else:
                status, payable = human["status"], (0.0 if human["status"] == "reject" else float(human["payable_amount"]))
            final = {"status": status, "payable_amount": payable, "source": "human", "reviewer": human.get("reviewer"),
                     "notes": human.get("notes"), "cited_clause_ids": ai.get("cited_clause_ids", []), "reasons": ai.get("reasons", []),
                     "override": (status != ai.get("decision")) or (payable != ai.get("payable_amount"))}
        final["ai_recommendation"] = {"status": ai.get("decision"), "payable_amount": ai.get("payable_amount")}
        final["escalation_reasons"] = state.get("escalation_reasons", [])
        return {"final": final, "audit": [_event("finalise", status=final["status"], source=final["source"], override=final["override"])]}

    # ------------------------------------------------------------------ edges
    def after_extract(state):
        return "route" if state.get("extraction_error") else "security_scan"

    def after_validate(state):
        return "route" if state.get("validation_flags") else "read_policy"

    def after_verify(state):
        if state["verifier"]["passed"]:
            return "route"
        # attempts so far = retries['read_policy']; the first read is attempt 1
        return "read_policy" if state["retries"]["read_policy"] <= cfg.max_verify_retries else "route"

    def after_route(state):
        return "human_review" if state.get("needs_human") else "finalise"

    g = StateGraph(ClaimState)
    for name, fn in (("extract", extract), ("security_scan", security), ("validate", validate_node), ("read_policy", read_policy),
                     ("decide", decide), ("verify", verify), ("route", route), ("human_review", human_review), ("finalise", finalise)):
        g.add_node(name, fn)
    g.add_edge(START, "extract")
    g.add_conditional_edges("extract", after_extract, {"route": "route", "security_scan": "security_scan"})
    g.add_edge("security_scan", "validate")
    g.add_conditional_edges("validate", after_validate, {"route": "route", "read_policy": "read_policy"})
    g.add_edge("read_policy", "decide")
    g.add_edge("decide", "verify")
    g.add_conditional_edges("verify", after_verify, {"route": "route", "read_policy": "read_policy"})
    g.add_conditional_edges("route", after_route, {"human_review": "human_review", "finalise": "finalise"})
    g.add_edge("human_review", "finalise")
    g.add_edge("finalise", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


# ---------------------------------------------------------------------- helpers for API / UI / eval
def sqlite_checkpointer(path: str = "data/checkpoints.sqlite"):
    """Persistent checkpointer so a paused review survives a restart. Needs: pip install langgraph-checkpoint-sqlite"""
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def _result(graph, config) -> dict:
    snap = graph.get_state(config)
    if snap.next:   # paused at human_review
        packet = next((i.value for t in snap.tasks for i in t.interrupts), None)
        return {"status": "awaiting_human", "packet": packet, "state": snap.values}
    return {"status": "completed", "final": snap.values.get("final"), "state": snap.values}


def run_claim(graph, inputs: dict, thread_id: str) -> dict:
    """Start a claim. Returns {'status': 'completed', 'final': ...} or {'status': 'awaiting_human', 'packet': ...}."""
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"claim_id": thread_id, **inputs}, config)
    return _result(graph, config)


def resume_claim(graph, thread_id: str, action: dict) -> dict:
    """Resume a paused claim with {'action': 'approve'|'edit'|'reject', 'reviewer': ..., 'notes': ..., 'status'/'payable_amount' for edit}."""
    config = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(config)
    if not snap.next:
        raise ValueError(f"claim {thread_id} is not waiting for a human")
    validate_human_action(action, (snap.values.get("decision") or {}).get("decision"))
    graph.invoke(Command(resume=action), config)
    return _result(graph, config)