"""API request and response schemas for MediClaim-AI."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class ClaimSummary(BaseModel):
    id: str
    policy_id: str
    patient_name: Optional[str] = None
    status: Literal["approve", "partial", "reject", "needs_review", "pending"]
    billed_amount: float
    payable_amount: Optional[float] = None
    category: Optional[str] = None
    created_time: str
    assignee: Optional[str] = None
    flags: list[str] = []
    reasons: list[str] = []


class ClaimStatusResponse(BaseModel):
    claim_id: str
    status: str
    stage_states: dict[str, str]  # read_documents, extract_fields, validate, read_policy, decide
    timings: dict[str, float]
    current_stage: Optional[str] = None
    message: Optional[str] = None


class DeductionItem(BaseModel):
    rule: str
    amount: float
    clause_id: Optional[str] = None
    note: Optional[str] = None


class DecisionDetail(BaseModel):
    decision: str
    payable_amount: Optional[float] = None
    deductions: list[DeductionItem] = []
    cited_clause_ids: list[str] = []
    reasons: list[str] = []
    flags: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}
    retrieved_clause_ids: list[str] = []
    verifier: Optional[dict[str, Any]] = None
    escalation_reasons: list[str] = []


class ReviewAuditEntry(BaseModel):
    review_id: str
    claim_id: str
    reviewer: str
    action: str  # confirm, override, request_docs
    reason: Optional[str] = None
    created_time: str
    field_edits: list[dict[str, Any]] = []


class ClaimDetail(BaseModel):
    id: str
    policy_id: str
    patient_name: Optional[str] = None
    status: str
    billed_amount: float
    payable_amount: Optional[float] = None
    category: Optional[str] = None
    files_dir: Optional[str] = None
    files: list[str] = []
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    created_time: str
    assignee: Optional[str] = None
    decision: Optional[DecisionDetail] = None
    extracted: Optional[dict[str, Any]] = None
    stage_states: Optional[dict[str, str]] = None
    timings: Optional[dict[str, float]] = None
    audit_timeline: list[ReviewAuditEntry] = []


class FieldEditItem(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any


class ReviewSubmitRequest(BaseModel):
    reviewer: str = Field(..., min_length=1)
    action: Literal["confirm", "override", "request_docs"]
    reason: Optional[str] = None
    field_edits: list[FieldEditItem] = []
    override_status: Optional[str] = None
    override_payable: Optional[float] = None


class RerunDecisionRequest(BaseModel):
    field_updates: dict[str, Any]


class RerunDecisionResponse(BaseModel):
    claim_id: str
    previous_decision: str
    previous_payable: Optional[float] = None
    new_decision: str
    new_payable: Optional[float] = None
    deductions: list[dict[str, Any]] = []
    reasons: list[str] = []
    cited_clause_ids: list[str] = []
    flags: list[str] = []
    difference: float = 0.0


class PolicySearchResult(BaseModel):
    policy_id: str
    clause_id: str
    parent_id: Optional[str] = None
    section: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    score: float
    child_text: Optional[str] = None
    text: str
    retriever_source: str = "hybrid"


class PolicyClauseNode(BaseModel):
    clause_id: str
    section: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    text: str
    preview: str

