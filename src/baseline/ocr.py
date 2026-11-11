"""Naive document reading: use the PDF text layer when there is one, otherwise run Tesseract on the page image.

Needs the Tesseract program installed (macOS: brew install tesseract). It is called as a command, so no extra
Python package is required. Results are cached next to the claim so repeated runs are free.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

MIN_TEXT_CHARS = 30


_RAPID = None


def rapid_engine():
    """RapidOCR (ONNX models bundled in the pip package) gives the same text on every machine. None if not installed."""
    global _RAPID
    if _RAPID is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID = RapidOCR()
        except ImportError:
            _RAPID = False
    return _RAPID or None


def engine_name() -> str:
    pref = os.environ.get("OCR_ENGINE", "").lower()
    if pref == "tesseract":
        return "tesseract"
    return "rapidocr" if rapid_engine() else "tesseract"


def rows_from_boxes(boxes: list[tuple[float, float, float, str]]) -> str:
    """boxes: (y_center, x_left, height, text). Detected boxes for a label and its value sit at slightly different heights,
    so cluster by vertical distance relative to text height and read each row left to right."""
    if not boxes:
        return ""
    boxes = sorted(boxes)
    tol = 0.7 * sorted(b[2] for b in boxes)[len(boxes) // 2]
    rows, cur, anchor = [], [boxes[0]], boxes[0][0]
    for b in boxes[1:]:
        if b[0] - anchor > tol:
            rows.append(cur)
            cur, anchor = [b], b[0]
        else:
            cur.append(b)
    rows.append(cur)
    return "\n".join(" ".join(t for _, _, _, t in sorted(r, key=lambda b: b[1])) for r in rows)


def _rapid_page_text(page, dpi: int) -> str:
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    result, _ = rapid_engine()(img)
    boxes = []
    for box, text, _score in result or []:
        ys, xs = [p[1] for p in box], [p[0] for p in box]
        boxes.append((sum(ys) / 4, min(xs), max(ys) - min(ys), text))
    return rows_from_boxes(boxes)


_WAIT_ROW = re.compile(r"waiting\s*per", re.I)


def waiting_rows_missing_values(text: str) -> int:
    """Count schedule rows labelled 'Waiting period ...' (other than the initial 30-day one) that have no digit.
    On degraded scans RapidOCR sometimes reads the label but drops the value cell."""
    return sum(1 for ln in text.splitlines()
               if _WAIT_ROW.search(ln) and not re.search(r"initial", ln, re.I) and not re.search(r"\d", ln))


RAPID_RETRY_DPIS = (300, 400)


def robust_rapid_text(page) -> str:
    """Normal RapidOCR pass; if waiting-period values are missing, retry at higher DPI, then Tesseract, keeping
    whichever read recovers the most values. Costs nothing on pages that read cleanly the first time."""
    text = _rapid_page_text(page, RAPID_DPI)
    missing = waiting_rows_missing_values(text)
    for dpi in RAPID_RETRY_DPIS:
        if not missing:
            return text
        retry = _rapid_page_text(page, dpi)
        if waiting_rows_missing_values(retry) < missing:
            text, missing = retry, waiting_rows_missing_values(retry)
    if missing and tesseract_available():
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            page.get_pixmap(dpi=OCR_DPI).save(png)
            retry = _ocr_image(png)
        if waiting_rows_missing_values(retry) < missing:
            text = retry
    return text


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_image(png: Path) -> str:
    r = subprocess.run(["tesseract", str(png), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=120)
    return r.stdout


RAPID_DPI = 200
OCR_DPI = 300   # 200 misread small digits on degraded scans ('12 months' read as '42 months'); 300 fixed 9 of 10 such pages


def read_pdf(path: Path, dpi: int = OCR_DPI) -> tuple[str, str]:
    """Returns (text, method) where method is 'text_layer' or 'ocr'."""
    doc = pymupdf.open(path)
    pages, method = [], "text_layer"
    for page in doc:
        txt = page.get_text()
        if len(txt.strip()) >= MIN_TEXT_CHARS:
            pages.append(txt)
            continue
        method = "ocr"
        if engine_name() == "rapidocr":
            pages.append(robust_rapid_text(page))
            continue
        if not tesseract_available():
            raise RuntimeError("No OCR engine found. Run: pip install rapidocr-onnxruntime   (or brew install tesseract)")
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            page.get_pixmap(dpi=dpi).save(png)
            pages.append(_ocr_image(png))
    return "\n".join(pages), method


OCR_VERSION = "r2"


def ocr_stamp_tag() -> str:
    return f"{engine_name()}-{OCR_DPI}-{RAPID_DPI}-{OCR_VERSION}"


def read_claim_docs(claim_dir: Path, use_cache: bool = True) -> dict[str, dict]:
    """Reads every PDF in claim_dir/docs. Returns {doc_name: {"text":..., "method":...}}."""
    cache = claim_dir / "docs" / "ocr_cache.json"
    pdfs = sorted((claim_dir / "docs").glob("*.pdf"))
    stamp = {p.name: p.stat().st_size for p in pdfs} | {"_ocr": ocr_stamp_tag()}   # a re-rendered or added PDF invalidates the cache
    if use_cache and cache.exists():
        saved = json.loads(cache.read_text())
        if saved.get("_files") == stamp:
            return {k: v for k, v in saved.items() if k != "_files"}
    out = {}
    for pdf in pdfs:
        text, method = read_pdf(pdf)
        out[pdf.stem] = {"text": text, "method": method}
    cache.write_text(json.dumps({**out, "_files": stamp}, indent=1))
    return out


def page_images(pdf: Path, dpi: int = 150, max_pages: int = 2) -> list[bytes]:
    """PNG bytes of the first pages, for sending to a vision model."""
    import pymupdf
    doc = pymupdf.open(pdf)
    return [page.get_pixmap(dpi=dpi).tobytes("png") for page in list(doc)[:max_pages]]