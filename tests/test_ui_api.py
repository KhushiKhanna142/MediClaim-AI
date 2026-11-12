"""Unit tests for the MediClaim-AI API and Service Layer."""
from __future__ import annotations

import pytest
from src.api.client import get_client
from src.api.models import FieldEditItem, ReviewSubmitRequest
from src.api.service import MediClaimService


@pytest.fixture
def service(tmp_path):
    db_file = tmp_path / "test_mediclaim.db"
    return MediClaimService(db_path=db_file)


def test_list_and_get_seeded_claims(service):
    claims = service.list_claims()
    assert len(claims) == 30

    # Test clean approve C001
    c1 = service.get_claim("C001_niva_clean_approve")
    assert c1 is not None
    assert c1.status == "approve"
    assert c1.payable_amount == 82800.0
    assert c1.decision is not None
    assert "4.1.2" in c1.decision.cited_clause_ids


def test_flagged_claims_land_in_review_queue(service):
    queue = service.list_claims(status="needs_review")
    queue_ids = [c.id for c in queue]
    assert len(queue_ids) >= 4
    # Missing documents and total mismatch must be in review queue
    assert "C014_niva_missing_docs" in queue_ids
    assert "C015_niva_total_mismatch" in queue_ids


def test_assign_claim_locks_to_reviewer(service):
    claim_id = "C015_niva_total_mismatch"
    ok = service.assign_claim(claim_id, "Dr. Sarah Chen")
    assert ok is True

    claim = service.get_claim(claim_id)
    assert claim.assignee == "Dr. Sarah Chen"


def test_rerun_decision_updates_payable_amount_deterministically(service):
    # C015 has a total mismatch: items add to 74900, bill total is 75900
    claim_id = "C015_niva_total_mismatch"
    c_before = service.get_claim(claim_id)
    assert c_before.status == "needs_review"

    # Adjust bill total to match items sum (74900)
    res = service.rerun_decision(claim_id, req=type("Req", (), {"field_updates": {"bill_total": 74900, "claimed_total": 74900}})())
    assert res.claim_id == claim_id
    assert res.new_decision in ("approve", "partial")
    assert res.new_payable is not None and res.new_payable > 0


def test_safety_rule_edit_never_changes_policy_findings(service):
    claim_id = "C001_niva_clean_approve"
    c_before = service.get_claim(claim_id)
    orig_findings = dict(c_before.decision.findings)

    # Re-run with changed bill total
    service.rerun_decision(claim_id, req=type("Req", (), {"field_updates": {"bill_total": 90000}})())
    c_after = service.get_claim(claim_id)

    # Findings regarding waiting periods, policy clauses, etc., must remain strictly unchanged
    assert c_after.decision.findings["initial_waiting_days"] == orig_findings["initial_waiting_days"]
    assert c_after.decision.findings["initial_wait_clause"] == orig_findings["initial_wait_clause"]
    assert c_after.decision.findings["coverage_clause"] == orig_findings["coverage_clause"]


def test_review_action_logs_immutable_audit_trail(service):
    claim_id = "C015_niva_total_mismatch"
    req = ReviewSubmitRequest(
        reviewer="Dr. Sarah Chen",
        action="confirm",
        reason="Verified corrected bill with hospital billing desk.",
        field_edits=[FieldEditItem(field_name="bill_total", old_value=75900, new_value=74900)],
    )
    service.submit_review(claim_id, req)

    claim = service.get_claim(claim_id)
    assert len(claim.audit_timeline) >= 1
    latest_audit = claim.audit_timeline[-1]
    assert latest_audit.reviewer == "Dr. Sarah Chen"
    assert latest_audit.action == "confirm"
    assert "Verified corrected bill" in latest_audit.reason
    assert latest_audit.field_edits[0]["field_name"] == "bill_total"


def test_demo_submission_creates_run_and_stages(service):
    new_id = service.create_claim_from_demo("C001_niva_clean_approve")
    assert new_id is not None
    st = service.get_claim_status(new_id)
    assert st is not None
    assert "read_documents" in st.stage_states
    assert "extract_fields" in st.stage_states
    assert "validate" in st.stage_states

