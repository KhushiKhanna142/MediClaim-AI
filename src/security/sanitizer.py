"""Security sanitizer and prompt-injection detector for medical claim documents.

Defences in order:
1. Scan raw document and OCR text BEFORE extraction to intercept injection attempts before any LLM sees them.
2. Scan PDF text layers for hidden text (tiny fonts < 2pt, white-on-white text, invisible render modes).
3. Sanitize/redact detected attack payloads to prevent downstream LLM hijacking.
4. Delimit untrusted document data explicitly in LLM prompts (<untrusted_document_data>).
5. Escalate any flagged claim to human review with specific security audit reasons.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

log = logging.getLogger(__name__)

# Patterns targeting prompt injection vectors
INJECTION_PATTERNS = [
    # 1. Direct instruction overrides and jailbreaks
    re.compile(r"\b(ignore|disregard|forget|override|cancel|bypass)\s+(all\s+|any\s+)?(previous|prior|above|system|adjudication|policy|rules?)\s+(instructions?|rules?|prompts?|guidelines?|constraints?)\b", re.I),
    re.compile(r"\b(new\s+instructions?|system\s+override|admin\s+mode|root\s+access|developer\s+mode|god\s+mode)\s*:\b", re.I),
    re.compile(r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(an?\s+)?(unrestricted|unconstrained|ai|assistant|auditor|irda|admin)\b", re.I),

    # 2. Financial / approval manipulation commands
    re.compile(r"\b(approve\s+(this\s+claim|in\s+full|immediately|for\s+full\s+amount))\b", re.I),
    re.compile(r"\b(set|force|change|override)\s+(status|decision|payable|amount)\s*(=|to|\:)\s*(approve|approved|100%|[0-9]+)\b", re.I),
    re.compile(r"\b(mark\s+(this\s+as\s+)?(fully\s+)?(approved|payable|clean|valid))\b", re.I),
    re.compile(r"\b(do\s+not\s+apply|skip|ignore|waive)\s+(any\s+)?(deductions?|exclusions?|co-?pay|waiting\s+periods?|ped|room\s+cap)\b", re.I),
    re.compile(r"\bpay\s+(the\s+)?(full|entire)\s+(amount|claim|sum|bill)\b", re.I),

    # 3. PED / exclusion suppression
    re.compile(r"\b(set|mark|state|force)\s+(is_pre_existing|is_ped|pre_existing)\s*(=|to|\:)\s*(false|null|no)\b", re.I),
    re.compile(r"\b(do\s+not\s+flag|suppress|hide)\s+(the\s+)?(pre-?existing|ped|waiting\s+period)\b", re.I),
    re.compile(r"\bno\s+waiting\s+period\s+applies\s+to\s+this\s+claim\b", re.I),

    # 4. Critic / verifier manipulation
    re.compile(r"\b(mark\s+this\s+as\s+supported|tell\s+the\s+verifier|verifier\s+must\s+pass|critic\s+override|output\s+supported\s*:\s*true)\b", re.I),
    re.compile(r"\b(ignore\s+verifier|bypass\s+verification|skip\s+adversarial\s+review)\b", re.I),

    # 5. System prompt exfiltration
    re.compile(r"\b(print|repeat|output|reveal|leak|show|display)\s+(the\s+)?(full\s+)?(system\s+prompt|initial\s+instructions?|hidden\s+prompt|developer\s+instructions?)\b", re.I),
    re.compile(r"\bwhat\s+(are\s+your|is\s+your)\s+(system\s+prompt|instructions?|hidden\s+rules?)\b", re.I),

    # 6. Delimiter hijacking and structured format injection
    re.compile(r"<\/?(system|instruction|system_instruction|assistant|human|admin|override|untrusted_document_data)>", re.I),
    re.compile(r"\[(SYSTEM(\s+OVERRIDE)?|ADMIN(\s+MODE)?|OVERRIDE|INSTRUCTION|DEVELOPER\s+MODE|DAN)\]", re.I),
    re.compile(r"```json\s*\{\s*\"(decision|status|payable_amount|action)\"\s*:\s*\"approve\"", re.I),
]


def scan_text(text: str) -> list[str]:
    """Scan arbitrary text for prompt injection patterns. Returns list of matched pattern flags."""
    if not text:
        return []
    flags = []
    for pat in INJECTION_PATTERNS:
        match = pat.search(text)
        if match:
            flags.append(f"security:prompt_injection:{match.group(0)[:60]}")
    return sorted(list(set(flags)))


def sanitize_text(text: str) -> tuple[str, list[str]]:
    """Scan text, sanitize any detected injection attacks by redacting them, and return (clean_text, flags)."""
    if not text:
        return text, []
    flags = []
    sanitized = text
    for pat in INJECTION_PATTERNS:
        matches = list(pat.finditer(sanitized))
        if matches:
            for m in reversed(matches):
                snippet = m.group(0)
                flags.append(f"security:prompt_injection:{snippet[:60]}")
                sanitized = sanitized[:m.start()] + "[REDACTED_SECURITY_THREAT]" + sanitized[m.end():]
    return sanitized, sorted(list(set(flags)))


def scan_pdf_hidden_text(pdf_path: Path | str) -> tuple[list[str], list[str]]:
    """Inspect a PDF file's text layer for hidden or adversarial content.
    Detects:
      - Tiny font sizes (< 2.0 pt)
      - White text on white background (color == 0xFFFFFF / 16777215)
      - Text containing prompt injection patterns
    Returns (flags, snippets).
    """
    if not fitz:
        return [], []
    path = Path(pdf_path)
    if not path.exists():
        return [], []

    flags = []
    snippets = []
    try:
        doc = fitz.open(str(path))
        for pno, page in enumerate(doc):
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        stext = span.get("text", "").strip()
                        if not stext:
                            continue
                        size = span.get("size", 10.0)
                        color = span.get("color", 0)

                        # Tiny font detection (< 2.0 pt)
                        if size < 2.0:
                            flags.append("security:hidden_text_tiny_font")
                            snippets.append(f"p{pno+1} [size={size:.1f}pt]: {stext[:80]}")

                        # White text detection (0xFFFFFF = 16777215)
                        if color in (16777215, 0xFFFFFF):
                            flags.append("security:hidden_text_white_font")
                            snippets.append(f"p{pno+1} [color=white]: {stext[:80]}")

                        # Check span text directly for injection
                        span_injections = scan_text(stext)
                        if span_injections:
                            flags.extend(span_injections)
                            snippets.append(f"p{pno+1} [injection]: {stext[:80]}")
    except Exception as exc:  # noqa: BLE001
        log.warning("PDF security scan failed for %s: %r", path.name, exc)

    return sorted(list(set(flags))), snippets


def scan_document_bundle(claim_dir: Path | str) -> list[str]:
    """Scan all PDFs in a claim bundle directory for hidden text and prompt injections."""
    pdir = Path(claim_dir)
    docs_dir = pdir / "docs" if (pdir / "docs").exists() else pdir
    if not docs_dir.exists():
        return []

    flags = []
    for pdf in docs_dir.glob("*.pdf"):
        pdf_flags, _ = scan_pdf_hidden_text(pdf)
        flags.extend(pdf_flags)
    return sorted(list(set(flags)))


def scan_extracted_claim(extracted: dict) -> list[str]:
    """Scan the dictionary of extracted fields for prompt injection attempts."""
    if not extracted:
        return []
    fields = [str(extracted.get(k) or "") for k in ("diagnosis", "known_history", "patient_name", "hospital")]
    fields += [str(i.get("description", "")) for i in extracted.get("items") or []]
    flags = []
    for val in fields:
        flags.extend(scan_text(val))
    return sorted(list(set(flags)))
