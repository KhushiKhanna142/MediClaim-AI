"""Extract only the English text from bilingual (Hindi + English) PDFs.

Works per text span, not per line, because bilingual headers often put Hindi and English
on the same line. Some Hindi spans are garbled by font encoding (e.g. 'पृʿ', 'संदभर्'),
so besides Devanagari we also drop spans containing modifier letters / Latin Extended
characters that never occur in normal English text.

CLI (from repo root):
    python -m src.ingestion.english_text data/regulations/IRDAI
Writes one JSON per PDF to data/processed/text/<name>.json and prints a drop report.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

DEVANAGARI = re.compile(r"[ऀ-ॿ꣠-ꣿ]")
# chars that only show up in mis-decoded Indic text, never in English prose
JUNK = re.compile(r"[Ā-ɏʰ-˿-�]")
# Latin-1 letters/accents are fine to keep only when rare; treated via ratio below
JUNK_RATIO_LIMIT = 0.10


def clean_span(text: str) -> str:
    """Return the span text if it is English, else an empty string."""
    if not text.strip():
        return text
    if DEVANAGARI.search(text):
        return ""
    junk = len(JUNK.findall(text))
    if junk:
        letters = max(len(re.findall(r"\w", text)), 1)
        if junk / letters > JUNK_RATIO_LIMIT:
            return ""
        text = JUNK.sub("", text)
    return text


SPACED_LETTERS = re.compile(r"^(?:\W*\d*\W*)?(?:[A-Za-z] ){2,}[A-Za-z]\W*$")  # 'P a g e'
GAZETTE_JUNK = re.compile(r"x{3}\w*x{3}", re.I)  # 'xxxGIDHxxx'
BILINGUAL_DROP_PCT = 20.0


LIST_MARKER = re.compile(r"^\(?(?:\d{1,3}(?:\.\d{1,3})*|[a-zA-Z]|[ivxIVX]{1,5})[.)]\)?$")  # '1.', '2.1.3', '(a)', '(iv)'


def is_residue(line: str) -> bool:
    """True for lines left over from stripped Hindi: numbers/punctuation, no real English words."""
    if LIST_MARKER.match(line.strip()):
        return False
    if GAZETTE_JUNK.search(line) or SPACED_LETTERS.match(line):
        return True
    return not any(len(w) >= 4 for w in re.findall(r"[A-Za-z]+", line))


def extract_english_pages(path: Path) -> tuple[list[dict], dict]:
    pages, total, kept = [], 0, 0
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            lines = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    raw = "".join(s["text"] for s in line["spans"])
                    total += len(raw.strip())
                    eng = "".join(clean_span(s["text"]) for s in line["spans"])
                    eng = re.sub(r"\s+", " ", eng).strip()
                    # drop lines that are only page-furniture or stray symbols
                    if len(re.findall(r"[A-Za-z0-9]", eng)) >= 2:
                        lines.append(eng)
                        kept += len(eng)
            pages.append({"page": pno, "lines": lines})
    dropped_pct = round(100 * (1 - kept / total), 1) if total else 0.0
    removed = 0
    if dropped_pct > BILINGUAL_DROP_PCT:  # bilingual document: also drop residue lines
        for pg in pages:
            keep = [ln for ln in pg["lines"] if not is_residue(ln)]
            removed += len(pg["lines"]) - len(keep)
            pg["lines"] = keep
    for pg in pages:
        pg["text"] = "\n".join(pg.pop("lines"))
    report = {"residue_lines_removed": removed, "file": str(path), "pages": len(pages),
              "chars_total": total, "chars_kept": kept,
              "dropped_pct": round(100 * (1 - kept / total), 1) if total else 0.0}
    return pages, report


def main(root: str) -> None:
    out_dir = Path("data/processed/text")
    out_dir.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(Path(root).rglob("*.pdf")):
        pages, rep = extract_english_pages(pdf)
        (out_dir / f"{pdf.stem}.json").write_text(
            json.dumps({"source": str(pdf), "pages": pages}, ensure_ascii=False, indent=1))
        sample = next((p["text"][:160].replace("\n", " | ") for p in pages if p["text"]), "")
        print(f"{pdf.name}: dropped {rep['dropped_pct']}% of text | sample: {sample}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/regulations")