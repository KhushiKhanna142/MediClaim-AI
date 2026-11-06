"""Check synthetic ground truth against the real indexed policy text.

  python -m synth.validate_ground_truth [--claims data/synthetic_claims] [--chunks data/processed/chunks]

1. Every expected clause id must exist as a parent clause in that policy's chunks (so the label is citable).
2. Lists rules that fired but have no clause id yet (unmapped), so you know which citations still need a mapping.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.rag.retriever import base_clause_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--chunks", default="data/processed/chunks")
    a = ap.parse_args()
    ids: dict[str, set[str]] = {}
    for f in Path(a.chunks).glob("*.jsonl"):
        ids[f.stem] = {base_clause_id(r["clause_id"]) for r in map(json.loads, f.read_text().splitlines()) if r["type"] == "parent"}
    missing, unmapped, n = defaultdict(set), Counter(), 0
    for gt_file in sorted(Path(a.claims).glob("*/ground_truth.json")):
        gt, n = json.loads(gt_file.read_text()), n + 1
        for cid in gt["expected_clause_ids"]:
            if cid not in ids.get(gt["policy_id"], set()):
                missing[gt["policy_id"]].add(cid)
        for d in gt["deductions"]:
            if not d["clause_id"]:
                unmapped[(gt["policy_id"], d["rule"])] += 1
        if gt["status"] in ("approve", "partial") and not gt["expected_clause_ids"]:
            unmapped[(gt["policy_id"], "coverage_clause")] += 1
    print(f"checked {n} claims")
    print("clause ids NOT found in the policy chunks:", {k: sorted(v) for k, v in missing.items()} or "none")
    print("rules with no clause id yet (policy, rule): count")
    for k, v in sorted(unmapped.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()