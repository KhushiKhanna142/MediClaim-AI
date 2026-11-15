"""Langfuse tracing with pre-transmission PII masking for claim adjudication.

Tracks per-claim traces, latencies, and LLM call counts.
All prompts, model outputs, and metadata are scrubbed for PII using src.security.pii
BEFORE anything is sent to external observability services.
"""
from __future__ import annotations

import contextvars
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

from src.security.pii import mask_dict_pii, redact_pii

# Context variable holding the currently active ClaimTrace in the execution context
_ACTIVE_TRACE: contextvars.ContextVar[Optional[ClaimTrace]] = contextvars.ContextVar("active_trace", default=None)

# Registry of completed claim traces in the current process
_TRACE_REGISTRY: list[ClaimTrace] = []

_LANGFUSE_CLIENT = None
_LANGFUSE_INITIALIZED = False


def _get_langfuse_client():
    global _LANGFUSE_CLIENT, _LANGFUSE_INITIALIZED
    if _LANGFUSE_INITIALIZED:
        return _LANGFUSE_CLIENT

    _LANGFUSE_INITIALIZED = True
    pub_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not pub_key or not sec_key:
        _LANGFUSE_CLIENT = None
        return None

    try:
        from langfuse import Langfuse
        host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
        _LANGFUSE_CLIENT = Langfuse(public_key=pub_key, secret_key=sec_key, host=host)
    except Exception:
        _LANGFUSE_CLIENT = None

    return _LANGFUSE_CLIENT


@dataclass
class LLMGeneration:
    model: str
    prompt: str
    output: str
    duration_s: float
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimTrace:
    claim_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_s: float = 0.0
    llm_calls: int = 0
    generations: list[LLMGeneration] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def finish(self) -> None:
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_s = max(0.0, self.end_time - self.start_time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "duration_s": round(self.duration_s, 3),
            "llm_calls": self.llm_calls,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


def get_active_trace() -> Optional[ClaimTrace]:
    """Return the currently active claim trace, if any."""
    return _ACTIVE_TRACE.get()


@contextmanager
def trace_claim(
    claim_id: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[ClaimTrace, None, None]:
    """Context manager for tracing the end-to-end lifecycle of a claim.

    Sanitizes all metadata before storing or transmitting.
    """
    safe_metadata = mask_dict_pii(metadata or {})
    trace = ClaimTrace(
        claim_id=claim_id,
        tags=list(tags or []),
        metadata=safe_metadata,
    )
    token = _ACTIVE_TRACE.set(trace)

    client = _get_langfuse_client()
    obs_ctx = None
    if client is not None:
        try:
            obs_ctx = client.start_as_current_observation(
                name=f"claim_{claim_id}",
                as_type="span",
                metadata=safe_metadata,
            )
            obs_ctx.__enter__()
        except Exception:
            obs_ctx = None

    try:
        yield trace
    finally:
        trace.finish()
        if obs_ctx is not None:
            try:
                obs_ctx.__exit__(None, None, None)
            except Exception:
                pass
        _ACTIVE_TRACE.reset(token)
        _TRACE_REGISTRY.append(trace)


def record_llm_call(
    model: str,
    system: str,
    user: str,
    output: str,
    duration_s: float,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an LLM call under the currently active claim trace.

    Applies PII redaction to system prompt, user prompt, and output BEFORE recording.
    """
    safe_system = redact_pii(system or "")
    safe_user = redact_pii(user or "")
    safe_output = redact_pii(output or "")
    safe_meta = mask_dict_pii(metadata or {})
    full_prompt = f"SYSTEM:\n{safe_system}\n\nUSER:\n{safe_user}" if safe_system else safe_user

    gen = LLMGeneration(
        model=model,
        prompt=full_prompt,
        output=safe_output,
        duration_s=duration_s,
        timestamp=time.time(),
        metadata=safe_meta,
    )

    active = _ACTIVE_TRACE.get()
    if active is not None:
        active.llm_calls += 1
        active.generations.append(gen)

    client = _get_langfuse_client()
    if client is not None:
        try:
            with client.start_as_current_observation(
                name="llm_call",
                as_type="generation",
                model=model,
                input=full_prompt,
                metadata=safe_meta,
            ) as obs:
                obs.update(output=safe_output)
        except Exception:
            pass


def flush_tracing() -> None:
    """Flush any queued traces to the Langfuse backend."""
    client = _get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass


def clear_trace_registry() -> None:
    """Clear in-memory trace registry (useful for testing and batch boundaries)."""
    global _TRACE_REGISTRY
    _TRACE_REGISTRY.clear()


def get_all_trace_stats() -> list[dict[str, Any]]:
    """Return summary dictionary for all completed traces in this process."""
    return [t.to_dict() for t in _TRACE_REGISTRY]


def get_trace_stats() -> dict[str, Any]:
    """Compute aggregate speed and LLM call metrics across completed traces."""
    if not _TRACE_REGISTRY:
        return {"total_claims": 0, "avg_duration_s": 0.0, "avg_llm_calls": 0.0}

    n = len(_TRACE_REGISTRY)
    avg_dur = sum(t.duration_s for t in _TRACE_REGISTRY) / n
    avg_calls = sum(t.llm_calls for t in _TRACE_REGISTRY) / n
    return {
        "total_claims": n,
        "avg_duration_s": round(avg_dur, 2),
        "min_duration_s": round(min(t.duration_s for t in _TRACE_REGISTRY), 2),
        "max_duration_s": round(max(t.duration_s for t in _TRACE_REGISTRY), 2),
        "avg_llm_calls": round(avg_calls, 2),
        "min_llm_calls": min(t.llm_calls for t in _TRACE_REGISTRY),
        "max_llm_calls": max(t.llm_calls for t in _TRACE_REGISTRY),
    }
