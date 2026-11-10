"""Naive document reading: use the PDF text layer when there is one, otherwise run Tesseract on the page image.

Needs the Tesseract program installed (macOS: brew install tesseract). It is called as a command, so no extra
Python package is required. Results are cached next to the claim so repeated runs are free.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

MIN_TEXT_CHARS = 30


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_image(png: Path) -> str:
    r = subprocess.run(["tesseract", str(png), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=120)
    return r.stdout


def read_pdf(path: Path, dpi: int = 200) -> tuple[str, str]:
    """Returns (text, method) where method is 'text_layer' or 'ocr'."""
    import pymupdf
    doc = pymupdf.open(path)
    pages, method = [], "text_layer"
    for page in doc:
        txt = page.get_text()
        if len(txt.strip()) >= MIN_TEXT_CHARS:
            pages.append(txt)
            continue
        if not tesseract_available():
            raise RuntimeError("Tesseract is not installed. On macOS run: brew install tesseract")
        method = "ocr"
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            page.get_pixmap(dpi=dpi).save(png)
            pages.append(_ocr_image(png))
    return "\n".join(pages), method


def read_claim_docs(claim_dir: Path, use_cache: bool = True) -> dict[str, dict]:
    """Reads every PDF in claim_dir/docs. Returns {doc_name: {"text":..., "method":...}}."""
    cache = claim_dir / "docs" / "ocr_cache.json"
    pdfs = sorted((claim_dir / "docs").glob("*.pdf"))
    stamp = {p.name: p.stat().st_size for p in pdfs}   # a re-rendered or added PDF invalidates the cache
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