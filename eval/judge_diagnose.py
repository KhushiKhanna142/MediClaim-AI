"""Explain every RAGAS context-recall score below 1.0, using only the files the judge stage already wrote (stdlib only, no LLM calls).

  python3 -m eval.judge_diagnose

For each question the gold clause IDs are compared with the retrieved clause IDs (suffixes ~pN / #N ignored, as in eval.retrieval_eval):
  gold_not_retrieved       no gold clause is in the top-k            -> a real retrieval miss
  some_gold_missing        some, but not all, gold clauses retrieved  -> metric asks for more than recall@k does (any-hit)
  gold_retrieved_text_gap  every gold clause retrieved, recall < 1    -> the reference text is longer than what was retrieved
                                                                        (a clause split into pieces) or the judge is strict
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def base_id(cid: str) -> str:
    return re.split(r"[~#]", cid)[0]


def classify(row: dict, res: dict) -> str:
    gold = {base_id(g) for g in row["gold_clause_ids"]}
    got = {base_id(c) for c in row["retrieved_clause_ids"]}
    if not gold & got:
        return "gold_not_retrieved"
    if not gold <= got:
        return "some_gold_missing"
    return "gold_retrieved_text_gap"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="eval/results/judge_inputs_retrieval.jsonl")
    ap.add_argument("--results", default="eval/results/ragas_retrieval.json")
    a = ap.parse_args()
    rows = {r["id"]: r for r in map(json.loads, filter(str.strip, Path(a.inputs).read_text().splitlines()))}
    res = json.loads(Path(a.results).read_text())["results"]
    groups: dict[str, list] = {}
    for qid, v in res.items():
        if "error" in v or v["context_recall"] >= 0.999 or qid not in rows:
            continue
        r = rows[qid]
        groups.setdefault(classify(r, v), []).append((qid, r["set"], v["context_recall"], r))
    total_low = sum(len(g) for g in groups.values())
    print(f"{total_low} questions with context recall < 1.0\n")
    for name in ("gold_not_retrieved", "some_gold_missing", "gold_retrieved_text_gap"):
        items = groups.get(name, [])
        print(f"{name}: {len(items)}")
        for qid, s, rec, r in items:
            ref_chars = len(r["reference"])
            matched = sum(len(c) for c, cid in zip(r["retrieved_contexts"], r["retrieved_clause_ids"]) if base_id(cid) in {base_id(g) for g in r["gold_clause_ids"]})
            print(f"  {qid:34} {s:8} recall={rec:<5} gold={r['gold_clause_ids']} retrieved={r['retrieved_clause_ids']}  "
                  f"reference={ref_chars} chars, matching retrieved text={matched} chars")
    gap = groups.get("gold_retrieved_text_gap", [])
    if gap:
        print("\nIf 'matching retrieved text' is much shorter than 'reference' for most of the third group, the low recall comes from clauses split "
              "into pieces (a measurement artifact), not from retrieval failing.")


if __name__ == "__main__":
    main()