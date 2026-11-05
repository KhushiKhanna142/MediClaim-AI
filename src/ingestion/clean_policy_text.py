"""Turn raw per-page text (from english_text.py) into clean paragraphs for clause-aware chunking.

Fixes seen in the real policy PDFs:
  * repeated page headers/footers (insurer address, UIN line, '1 / 47') -> removed, but kept in `boilerplate`
  * letter-spaced words ('G o v e r n m e n t') -> collapsed
  * justified columns broken into one word per line (Star) -> lines rejoined into paragraphs
  * clause numbers on their own line (Niva: '2.1.7.' then text) -> glued to the following text
Paragraph boundaries are kept at clause numbers, lettered sub-items, bullets and SECTION/Def. headings.

CLI (from repo root):  python -m src.ingestion.clean_policy_text data/processed/text/<file>.json ...
Writes data/processed/clean/<stem>.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

BOILERPLATE_MIN_FRAC = 0.4     # line present on >= 40% of pages counts as header/footer
BOILERPLATE_MIN_LEN = 12
MIN_PAGES_FOR_BOILERPLATE = 6

MARKER_ONLY = re.compile(r"^(?:\(?\d{1,3}(?:\.\d{1,3})*[.)]\)?|\(?[a-zA-Z]{1,3}[.)]\)?|[ivxIVX]{1,5}[.)])$")
PARA_START = re.compile(
    r"^(?:\d{1,3}(?:\.\d{1,3})*\.?\s+\S"        # 2.1.7. Text   /  4. Text
    r"|\(?[a-zA-Z0-9]{1,3}[.)]\s+\S"            # (a) Text  /  a. Text  / i) Text
    r"|[•●▪■o]\s+\S"                           # bullets
    r"|SECTION\b|PART\b|ANNEXURE\b|Annexure\b|Def\.\s*\d+|Section\s+(?:\d|[A-D]\b))"
)
PAGE_NUM = re.compile(r"^(?:page\s*)?\d{1,4}\s*(?:/|of|\|)\s*\d{1,4}$", re.I)   # '1 / 47', 'Page 3 of 10'
LETTER_SPACED = re.compile(r"(?<![A-Za-z])(?:[A-Za-z] ){3,}[A-Za-z](?![A-Za-z])")


def _norm_for_repeat(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def find_boilerplate(pages: list[str]) -> set[str]:
    if len(pages) < MIN_PAGES_FOR_BOILERPLATE:
        return set()
    counts: Counter[str] = Counter()
    for text in pages:
        seen = {_norm_for_repeat(ln) for ln in text.split("\n") if len(ln.strip()) >= BOILERPLATE_MIN_LEN}
        counts.update(seen)
    limit = BOILERPLATE_MIN_FRAC * len(pages)
    return {k for k, c in counts.items() if c >= limit}


def despace_letters(line: str) -> str:
    return LETTER_SPACED.sub(lambda m: m.group(0).replace(" ", ""), line)


def lines_to_paragraphs(lines: list[str]) -> list[str]:
    paras: list[str] = []
    pending_marker = ""
    for raw in lines:
        ln = despace_letters(raw.strip())
        if not ln:
            continue
        if MARKER_ONLY.match(ln):                 # '2.1.7.' alone on a line
            if pending_marker:
                paras.append(pending_marker)
            pending_marker = ln
            continue
        if pending_marker:
            paras.append(f"{pending_marker} {ln}")
            pending_marker = ""
            continue
        if paras and not PARA_START.match(ln):
            paras[-1] += " " + ln
        else:
            paras.append(ln)
    if pending_marker:
        paras.append(pending_marker)
    return [re.sub(r"\s+", " ", p).strip() for p in paras]


def clean_document(raw_pages: list[dict]) -> dict:
    texts = [p["text"] for p in raw_pages]
    boiler = find_boilerplate(texts)
    removed: Counter[str] = Counter()
    out: list[dict] = []          # {"page": n, "text": paragraph}
    for p in raw_pages:
        kept = []
        for ln in p["text"].split("\n"):
            key = _norm_for_repeat(ln)
            if PAGE_NUM.match(ln.strip()):
                continue
            if len(ln.strip()) >= BOILERPLATE_MIN_LEN and key in boiler:
                removed[ln.strip()] += 1
            else:
                kept.append(ln)
        paras = lines_to_paragraphs(kept)
        for i, para in enumerate(paras):
            # paragraph continuing from the previous page: first para without a clause start
            if i == 0 and out and not PARA_START.match(para) and not re.search(r"[.:;]$", out[-1]["text"]):
                out[-1]["text"] += " " + para
            else:
                out.append({"page": p["page"], "text": para})
    return {"paragraphs": out, "boilerplate": [k for k, _ in removed.most_common(10)]}


def main(files: list[str]) -> None:
    out_dir = Path("data/processed/clean")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        d = json.loads(Path(f).read_text())
        res = clean_document(d["pages"])
        res["source"] = d["source"]
        (out_dir / Path(f).name).write_text(json.dumps(res, ensure_ascii=False, indent=1))
        n = len(res["paragraphs"])
        print(f"{Path(f).name}: {len(d['pages'])} pages -> {n} paragraphs, "
              f"{len(res['boilerplate'])} header/footer lines removed")


if __name__ == "__main__":
    main(sys.argv[1:])