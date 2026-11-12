"""Typed state that flows through the claim graph.

Everything in it is plain JSON (dicts, lists, strings, numbers) so any LangGraph checkpointer can persist it while the
graph waits for a human. Pydantic objects (ExtractedClaim, Findings) are stored as dicts and re-validated inside nodes.
Each node writes only its own keys; `audit` is append-only.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict


class ClaimState(TypedDict, total=False):
    # inputs (give either claim_dir, to run extraction, or extracted, to skip it)
    claim_id: str
    policy_id: str
    claim_dir: Optional[str]
    docs_present: list[str]
    extracted: Optional[dict[str, Any]]
    # extract / security / validate
    extraction_error: Optional[str]
    security_flags: list[str]
    validation_flags: list[str]
    validation_warnings: list[str]
    validation_details: list[str]
    # policy reading and decision
    findings: Optional[dict[str, Any]]
    retrieved_clause_ids: list[str]
    dropped_citations: list[str]
    decision: Optional[dict[str, Any]]          # the system's recommendation; never overwritten by the human
    # verification loop
    verifier: Optional[dict[str, Any]]
    verifier_feedback: Optional[str]
    retries: dict[str, int]
    # routing and human review
    needs_human: bool
    escalation_reasons: list[str]
    human_action: Optional[dict[str, Any]]
    # outcome
    final: Optional[dict[str, Any]]
    audit: Annotated[list[dict[str, Any]], operator.add]