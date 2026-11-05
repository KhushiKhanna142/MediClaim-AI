"""Clause-aware parent/child chunker for insurer policy wordings.

Parent = one clause (e.g. Care '2.1.17. Hospital ...', HDFC 'Def. 18.', Star 'Def:Room Rent', Star '13. Automatic
Restoration ...') including its lettered sub-items. Child = a piece of a parent of at most MAX_CHILD chars.
Retrieval embeds children; the answer context uses the parent. Every chunk carries policy metadata so retrieval can
filter by insurer / product / version / date and never mixes one insurer's rules into another's.

CLI (from repo root):  python -m src.rag.chunker
Reads  data/processed/clean/<stem>.json + data/policies/policies.json
Writes data/processed/chunks/<policy_id>.jsonl   (one JSON per line, type = parent | child)
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

MAX_CHILD = 900
MAX_PARENT = 3000
MIN_PARENT = 40

UIN = r"[A-Z]{3}HLIP\d{5}V\d{6}"
HEADER_PATTERNS = [  # page headers that leaked into paragraphs (seen in the real PDFs)
    re.compile(r"HDFC ERGO General Insurance Company Limited\.?\s*IRDAI Reg\. No\.\s*146.*?UIN:?\s*(?:my:)?\s*(?:Optima \w+\s*-\s*)?" + UIN, re.S),
    re.compile(r"HDFC ERGO General Insurance Company Limited\s*Policy Wording\s*(?:my:\s*)?Optima \w+"),
    re.compile(r"Care Supreme\s*-\s*" + UIN + r"(?:\s*Know Your Policy Better)?"),
    re.compile(r"STAR HEALTH AND ALLIED INSURANCE COMPANY LIMITED\s*POLICY WORDINGS\s*Star Comprehensive Insurance Policy\s*UIN\s*:\s*" + UIN + r"(?:\s*POL / COMP / V\.\d+ / \d{4})?"),
    re.compile(r"Product Name:\s*Aspire\s*\|\s*Product UIN:\s*" + UIN),
]

NUM = re.compile(r"^(\d{1,2}(?:\.\d{1,3})*)\.\s+\S")           # 2.1.17. Hospital ...   13. Automatic ...
HDFC_DEF = re.compile(r"^Def\.\s*(\d+)\.?")                      # Def. 18.
HDFC_SEC = re.compile(r"^(?:SECTION|Section)\s+([A-D](?:[.\-]\d+)?)\b")
ROMAN_ITEM = re.compile(r"^([IVX]{1,5})\.\s+[A-Z]")                 # 'XI. Portability' (old HDFC list items)
HDFC_LET = re.compile(r"^([A-D]\.\d+(?:\.\d+)?)\s+\S")           # B.1 Base Coverages
TERM = re.compile(r"^([A-Z][A-Za-z0-9()/&,'\- ]{2,70}?):\s+\S")  # Star-style 'Accident: An Accident means'
TERM_STOP = {"Note", "Provided", "Example", "Explanation", "Illustration", "Special Conditions", "Rs", "Exclusions"}
STAR_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z][A-Za-z0-9()/&,'\- ]{2,70}?:\s+[A-Z])")


HEAD_ROMAN = re.compile(r"^([IVX]{1,5})\s+[-–]\s+[A-Z][A-Z &/,()'\-]{3,}")   # 'I - DEFINITIONS' (not 'X-RAY')


RUNON = {"STANDARD", "SPECIFIC", "DEFINITIONS", "EXCLUSIONS", "BENEFITS", "COVERAGE", "GENERAL", "TERMS",
         "CONDITIONS", "WAITING", "PERIODS", "PERIOD", "AND", "OF", "THE", "POLICY", "CLAUSES", "COVERED"}


def _segment(tok: str) -> list[str] | None:
    """Split an all-caps run-on token into known words (shortest split); None if it can't be fully split."""
    best: list[list[str] | None] = [None] * (len(tok) + 1)
    best[0] = []
    for i in range(1, len(tok) + 1):
        for j in range(max(0, i - 12), i):
            if best[j] is not None and tok[j:i] in RUNON:
                cand = best[j] + [tok[j:i]]
                if best[i] is None or len(cand) < len(best[i]):
                    best[i] = cand
    return best[len(tok)]


def fix_runon_caps(text: str) -> str:
    """'STANDARDDEFINITIONS' (letter-spacing collapse) -> 'STANDARD DEFINITIONS' for long all-caps tokens."""
    return re.sub(r"\b[A-Z]{12,}\b", lambda m: " ".join(_segment(m.group(0)) or [m.group(0)]), text)


def leading_caps(text: str) -> str:
    """Leading all-caps words of a paragraph: 'II - COVERAGE In consideration...' -> 'II - COVERAGE'."""
    out = []
    for tok in text.split():
        if tok.isupper() or tok in {"-", "–", "&", "/"}:
            out.append(tok)
        else:
            break
    return " ".join(out)


def heading_label(text: str, cid: str | None) -> str:
    if HEAD_ROMAN.match(text) or text.startswith("SECTION"):
        return fix_runon_caps(leading_caps(text) or (cid or text[:60]))
    return fix_runon_caps(text[:80].strip())


def _caps_heading(text: str) -> bool:
    return (text.isupper() and len(text) <= 80 and not re.search(r"\d", text)
            and not text.rstrip().endswith("."))


def is_heading(text: str) -> bool:
    """Non-numeric headings: 'I - DEFINITIONS', 'SECTION B. BENEFITS', 'EXCLUSIONS'. Numbered headings need lookahead."""
    if len(text) > 100:
        return False
    return bool(HEAD_ROMAN.match(text) or HDFC_SEC.match(text) or _caps_heading(text))


def heading_kind(text: str, cid: str | None, next_cid: str | None) -> str | None:
    """'major' | 'sub' | None. A numbered paragraph is a heading only when the next clause is numbered under it."""
    if HEAD_ROMAN.match(text) or (HDFC_SEC.match(text) and len(text) <= 100):
        return "major"
    if _caps_heading(text):
        return "sub"
    if cid and next_cid and re.fullmatch(r"\d{1,2}(?:\.\d{1,3})*", cid) and next_cid.startswith(cid + "."):
        return "major" if "." not in cid else "sub"      # no length limit: heading may be merged with its first line
    return None


def struct_id(text: str, cid: str | None) -> str | None:
    """Identifier that can qualify bare list numbers: a hierarchical clause id, 'Section B', or a roman heading."""
    if m := HEAD_ROMAN.match(text):
        return m.group(1)
    if cid and ("." in cid or cid.startswith("Section") or re.match(r"[A-D]\.\d", cid)) and not cid.startswith("Def"):
        return cid
    return None


def _looks_like_toc_line(text: str) -> bool:
    return (text.startswith(("Section", "SECTION", "Annexure", "Part")) and len(text) <= 700
            and len(re.findall(r"\s\d{1,3}\s+[A-Z]", text)) >= 4)


def skip_toc_pages(paras: list[dict]) -> list[dict]:
    toc = {p["page"] for p in paras if re.match(r"^Table of Contents", p["text"], re.I)}
    return [p for p in paras if p["page"] not in toc and not _looks_like_toc_line(p["text"])]


def split_parent(paras: list[str], limit: int = MAX_PARENT) -> list[list[str]]:
    groups, cur, size = [], [], 0
    for para in paras:
        if cur and size + len(para) > limit:
            groups.append(cur)
            cur, size = [], 0
        cur.append(para)
        size += len(para)
    return groups + ([cur] if cur else [])


def strip_headers(text: str) -> str:
    for pat in HEADER_PATTERNS:
        text = pat.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_star_definitions(para: str) -> list[str]:
    parts, last = [], 0
    for m in STAR_SPLIT.finditer(para):
        nxt = para[m.end():]
        term = TERM.match(nxt)
        if term and term.group(1) not in TERM_STOP:
            parts.append(para[last:m.start()])
            last = m.end()
    parts.append(para[last:])
    return [p for p in parts if p.strip()]


def clause_id(text: str, insurer: str) -> str | None:
    if m := HDFC_DEF.match(text):
        return f"Def.{m.group(1)}"
    if (m := HDFC_SEC.match(text)) and (len(text) <= 100 or text.startswith("SECTION")
                                         or re.match(r"Section [A-D]\.\s", text)):
        return f"Section {m.group(1)}"
    if m := ROMAN_ITEM.match(text):
        return m.group(1)
    if m := HDFC_LET.match(text):
        return m.group(1)
    if m := NUM.match(text):
        return m.group(1)
    if insurer.startswith("Star") and (m := TERM.match(text)) and m.group(1) not in TERM_STOP:
        return f"Def:{m.group(1).strip()}"
    return None


def split_long(text: str, limit: int = MAX_CHILD) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.;:])\s+", text):
        if cur and len(cur) + len(s) + 1 > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def skip_front_matter(paras: list[dict], policy: dict) -> list[dict]:
    """Old HDFC file starts with a Customer Information Sheet: drop pages before the real wording."""
    if not str(policy.get("doc_ref") or "").upper().startswith("CIS"):
        return paras
    for p in paras:
        if re.match(r"^(Def\.\s*1\b|SECTION A|Section A)", p["text"]):
            return [q for q in paras if q["page"] >= p["page"]]
    return paras


def chunk_policy(paras: list[dict], policy: dict) -> list[dict]:
    insurer = policy["insurer"]
    base = {k: policy.get(k) for k in
            ("policy_id", "insurer", "product", "uin", "status", "effective_from", "effective_to", "source_type")}
    paras = skip_toc_pages(skip_front_matter(paras, policy))

    units: list[dict] = []
    for p in paras:
        text = strip_headers(p["text"])
        if not text:
            continue
        pieces = split_star_definitions(text) if insurer.startswith("Star") else [text]
        for piece in pieces:
            units.append({"page": p["page"], "text": piece})

    parents: list[dict] = []
    major, sub, struct = "", "", ""
    cids = [clause_id(u["text"], insurer) for u in units]
    for i, u in enumerate(units):
        text, cid = u["text"], cids[i]
        kind = heading_kind(text, cid, cids[i + 1] if i + 1 < len(units) else None)
        if kind == "major":
            major, sub = heading_label(text, cid), ""
        elif kind == "sub":
            sub = heading_label(text, cid)
        elif cid and cid.startswith("Section"):          # long 'Section B. Benefits In-patient ...' paragraph
            major, sub = (heading_label(text, cid) if text.startswith("SECTION") else cid), ""
        section = f"{major} > {sub}" if major and sub else (major or sub)
        st = struct_id(text, cid)
        if st:
            struct = st
        if cid and re.fullmatch(r"\d{1,2}|[IVX]{1,5}", cid) and struct and not HEAD_ROMAN.match(text):      # bare list number: qualify it
            cid = f"{struct}/{cid}"
        if kind and not cid:
            cid = "H:" + text[:40]
        if cid or not parents:
            parents.append({"clause_id": cid or "preamble", "section": section,
                            "paras": [text], "page_start": u["page"], "page_end": u["page"]})
        else:
            parents[-1]["paras"].append(text)
            parents[-1]["page_end"] = u["page"]

    records, seen = [], {}
    for par in parents:
        if len("\n".join(par["paras"])) < MIN_PARENT:
            continue
        n = seen[par["clause_id"]] = seen.get(par["clause_id"], 0) + 1
        groups = split_parent(par["paras"])
        for gi, group in enumerate(groups, 1):
            pid = f"{base['policy_id']}::{par['clause_id']}" + (f"#{n}" if n > 1 else "") + (f"~p{gi}" if len(groups) > 1 else "")
            records.append({**base, "type": "parent", "chunk_id": pid, "clause_id": par["clause_id"],
                            "section": par["section"], "page_start": par["page_start"],
                            "page_end": par["page_end"], "text": "\n".join(group)})
            buf, pieces = "", []
            for para in group:
                for piece in split_long(para):
                    if buf and len(buf) + len(piece) + 1 > MAX_CHILD:
                        pieces.append(buf)
                        buf = piece
                    else:
                        buf = f"{buf} {piece}".strip()
            if buf:
                pieces.append(buf)
            for i, piece in enumerate(pieces, 1):
                records.append({**base, "type": "child", "chunk_id": f"{pid}::c{i}", "parent_id": pid,
                                "clause_id": par["clause_id"], "section": par["section"],
                                "page_start": par["page_start"], "page_end": par["page_end"],
                                "context": f"{base['insurer']} | {base['product']} | {par['clause_id']} | {par['section']}",
                                "text": piece})
    return records


def main() -> None:
    policies = json.loads(Path("data/policies/policies.json").read_text())
    out_dir = Path("data/processed/chunks")
    out_dir.mkdir(parents=True, exist_ok=True)
    for pol in policies:
        stem = Path(pol["source_file"]).stem
        clean = Path("data/processed/clean") / f"{stem}.json"
        if not clean.exists():
            print(f"{pol['policy_id']}: missing {clean}")
            continue
        recs = chunk_policy(json.loads(clean.read_text())["paragraphs"], pol)
        (out_dir / f"{pol['policy_id']}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
        ch = [len(r["text"]) for r in recs if r["type"] == "child"]
        pa = [r for r in recs if r["type"] == "parent"]
        print(f"{pol['policy_id']}: {len(pa)} parents, {len(ch)} children, "
              f"child median {int(statistics.median(ch))} chars, parents>3000: {sum(len(p['text']) > 3000 for p in pa)}")


if __name__ == "__main__":
    main()