"""Profile every PDF under data/ so we can pick the right chunking strategy per document.

Usage (from repo root):  python scripts/inspect_pdfs.py
Writes data/pdf_inspection.json and prints a summary table.
"""
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")

UIN_RE = re.compile(r"\bUIN\s*[:\-]?\s*([A-Z0-9]{10,25})", re.I)
UIN_LOOSE = re.compile(r"\b([A-Z]{3,6}HLIP\d{5,8}V\d{6})\b")
VERSION_RE = re.compile(r"(?:version|ver\.?|v)\s*[:\-]?\s*(\d+(?:\.\d+)*)", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{4})\b")
# numbered clause headings such as "4.2", "4.2.1", "Section 3", "Clause 7(a)"
CLAUSE_RE = re.compile(r"^\s*((?:\d{1,2}\.){1,3}\d{0,2})\s+[A-Z][A-Za-z ,/&\-]{3,}", re.M)
SECTION_RE = re.compile(r"^\s*(SECTION|PART|ANNEXURE|ANNEXURE|SCHEDULE|CLAUSE)\b.*$", re.M | re.I)
KEYWORDS = ["waiting period", "room rent", "co-payment", "co-pay", "sub-limit", "sublimit",
            "pre-existing", "exclusion", "sum insured", "proportionate", "moratorium"]


def profile(path: Path) -> dict:
    doc = fitz.open(path)
    n = len(doc)
    chars = []
    for p in doc:
        chars.append(len(p.get_text("text").strip()))
    text_pages = sum(1 for c in chars if c > 200)
    full = "\n".join(doc[i].get_text("text") for i in range(n))
    head = "\n".join(doc[i].get_text("text") for i in range(min(3, n)))
    two_col_hint = 0
    for i in range(min(n, 10)):
        blocks = doc[i].get_text("blocks")
        xs = sorted({round(b[0] / 50) for b in blocks if len(b[4].strip()) > 80})
        if len(xs) >= 2 and (xs[-1] - xs[0]) >= 4:
            two_col_hint += 1
    clauses = CLAUSE_RE.findall(full)
    return {
        "file": str(path),
        "pages": n,
        "avg_chars_per_page": round(sum(chars) / max(n, 1)),
        "text_pages": text_pages,
        "likely_scanned": text_pages < 0.6 * n,
        "possible_two_column_pages_in_first_10": two_col_hint,
        "uin_candidates": sorted(set(UIN_RE.findall(head) + UIN_LOOSE.findall(full)))[:5],
        "version_candidates": sorted(set(VERSION_RE.findall(head)))[:5],
        "date_candidates_first_pages": sorted(set(DATE_RE.findall(head)))[:6],
        "numbered_clause_headings": len(clauses),
        "sample_clause_headings": [c.strip() if isinstance(c, str) else c for c in clauses[:8]],
        "section_headings_sample": [m.group(0).strip()[:80] for m in SECTION_RE.finditer(full)][:10],
        "keyword_hits": {k: len(re.findall(k, full, re.I)) for k in KEYWORDS},
        "has_toc": bool(doc.get_toc()),
        "first_page_snippet": " ".join(doc[0].get_text("text").split())[:300],
    }


def main():
    pdfs = sorted(ROOT.rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found under {ROOT}")
        return
    rows = []
    for p in pdfs:
        try:
            rows.append(profile(p))
        except Exception as e:  # keep going on a bad file
            rows.append({"file": str(p), "error": str(e)})
    out = ROOT / "pdf_inspection.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"{'file':60} {'pages':>5} {'chr/pg':>6} {'scan?':>5} {'clauses':>7} {'UIN'}")
    for r in rows:
        if "error" in r:
            print(f"{r['file'][:60]:60} ERROR {r['error']}")
            continue
        print(f"{r['file'][-60:]:60} {r['pages']:>5} {r['avg_chars_per_page']:>6} "
              f"{str(r['likely_scanned']):>5} {r['numbered_clause_headings']:>7} {r['uin_candidates'][:1]}")
    print(f"\nFull report written to {out}")


if __name__ == "__main__":
    main()