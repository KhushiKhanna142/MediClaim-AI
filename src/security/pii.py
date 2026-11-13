"""PII detection and masking before sending claim text to external LLM APIs.

Masks Aadhaar numbers, PAN cards, Indian phone numbers, email addresses, and IFSC codes
without altering clinical terms, dates, or rupee amounts.
"""
from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Aadhaar: 12 digits starting with 2-9, optionally grouped 4-4-4 by spaces or hyphens
    ("aadhaar", re.compile(r"\b[2-9]\d{3}(?:[\s\-]?\d{4}){2}\b"), "[AADHAAR_REDACTED]"),
    # PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
    ("pan", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN_REDACTED]"),
    # IFSC: 4 letters + '0' + 6 alphanumeric characters
    ("ifsc", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[IFSC_REDACTED]"),
    # Email addresses
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    # Indian mobile/phone numbers (+91 / 0 prefix optional, 10 digits starting with 6-9)
    ("phone", re.compile(r"(?<!\d)(?:\+91[\s\-]?|0)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)"), "[PHONE_REDACTED]"),
]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Mask PII patterns in text and return (masked_text, redaction_counts)."""
    if not text:
        return text, {}

    counts: dict[str, int] = {}
    masked = text
    for kind, pattern, replacement in _PATTERNS:
        masked, n = pattern.subn(replacement, masked)
        if n > 0:
            counts[kind] = counts.get(kind, 0) + n
    return masked, counts


def redact_pii(text: str) -> str:
    """Return text with all detected PII replaced by redaction placeholders."""
    masked, _ = mask_pii(text)
    return masked


def mask_dict_pii(obj: Any) -> Any:
    """Recursively mask PII in string values of a dict/list structure."""
    if isinstance(obj, str):
        return redact_pii(obj)
    if isinstance(obj, list):
        return [mask_dict_pii(x) for x in obj]
    if isinstance(obj, dict):
        return {k: mask_dict_pii(v) for k, v in obj.items()}
    return obj

