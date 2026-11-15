"""Tests for telemetry, Langfuse tracing wrapper, and PII masking before trace export."""
import os
import pytest

from src.llm import FakeLLM
from src.security.pii import redact_pii
from src.telemetry.tracing import (
    ClaimTrace,
    clear_trace_registry,
    get_active_trace,
    get_all_trace_stats,
    get_trace_stats,
    record_llm_call,
    trace_claim,
)


def test_pii_redaction_in_tracing():
    clear_trace_registry()
    # Prompt with sensitive Aadhaar and PAN and Phone
    raw_prompt = "Patient Aadhaar: 2345 6789 0123, PAN: ABCDE1234F, Phone: +91 9876543210"
    raw_output = "Approved for patient with Aadhaar 2345 6789 0123"

    with trace_claim("CLM_TEST_PII") as trace:
        record_llm_call(
            model="test-model",
            system="System with confidential email test@example.com",
            user=raw_prompt,
            output=raw_output,
            duration_s=0.25,
            metadata={"notes": "phone 9876543210"},
        )

    assert trace.llm_calls == 1
    gen = trace.generations[0]
    assert "2345 6789 0123" not in gen.prompt
    assert "[AADHAAR_REDACTED]" in gen.prompt
    assert "ABCDE1234F" not in gen.prompt
    assert "[PAN_REDACTED]" in gen.prompt
    assert "9876543210" not in gen.prompt
    assert "[PHONE_REDACTED]" in gen.prompt
    assert "test@example.com" not in gen.prompt
    assert "[EMAIL_REDACTED]" in gen.prompt

    # Check output redaction
    assert "2345 6789 0123" not in gen.output
    assert "[AADHAAR_REDACTED]" in gen.output

    # Check metadata redaction
    assert "9876543210" not in gen.metadata.get("notes", "")


def test_trace_claim_lifecycle_and_stats():
    clear_trace_registry()
    with trace_claim("CLM_LIFECYCLE_01") as trace:
        assert get_active_trace() is trace
        assert trace.claim_id == "CLM_LIFECYCLE_01"
        assert trace.llm_calls == 0

        # Simulate LLM calls
        llm = FakeLLM(reply="response 1")
        llm.complete("system", "user 1")
        llm.complete("system", "user 2")

        assert trace.llm_calls == 2

    assert get_active_trace() is None
    assert trace.duration_s >= 0.0
    assert trace.end_time is not None

    stats = get_trace_stats()
    assert stats["total_claims"] == 1
    assert stats["avg_llm_calls"] == 2.0


def test_graph_run_claim_records_telemetry():
    clear_trace_registry()
    from src.graph.workflow import build_graph, run_claim
    from src.adjudication.findings import Findings

    class MockReader:
        def read(self, claim, policy_id, refine=None, previous=None):
            return Findings(initial_waiting_days=30, is_specified=False, is_pre_existing=False), {
                "retrieved": {"coverage": ["4.1"]},
                "dropped_citations": [],
            }

    class MockVerifier:
        def verify(self, claim, findings, decision, retrieved_clause_ids):
            class Res:
                passed = True
                confidence = 1.0
                issues = []
                concerns = []
                def to_dict(self):
                    return {"passed": True, "confidence": 1.0, "issues": [], "concerns": []}
            return Res()

    from tests.test_graph import claim
    graph = build_graph(reader=MockReader(), verifier=MockVerifier())
    test_claim = claim()

    res = run_claim(graph, {"policy_id": "test_pol", "extracted": test_claim}, "test-trace-thread")
    assert "state" in res
    assert "telemetry" in res["state"]
    telemetry = res["state"]["telemetry"]
    assert telemetry["claim_id"] == "test-trace-thread"
    assert "duration_s" in telemetry
    assert "llm_calls" in telemetry
