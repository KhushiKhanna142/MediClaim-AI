"""Print every field where the saved extraction differs from claim.json.  python scripts/show_extraction.py [--limit 5]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.extraction_eval import CACHE, SCALARS, _norm

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=5)
a = ap.parse_args()
preds = json.loads(CACHE.read_text())
for cid in sorted(preds)[: a.limit]:
    if "error" in preds[cid]:
        print(cid, "ERROR", preds[cid]["error"][:200])
        continue
    claim = json.loads(Path(f"data/synthetic_claims/{cid}/claim.json").read_text())
    bad = [(n, preds[cid].get(n), g(claim)) for n, g in SCALARS if _norm(preds[cid].get(n)) != _norm(g(claim))]
    print(cid, "all fields match" if not bad else "")
    for n, got, want in bad:
        print(f"    {n:28} got {got!r:28} expected {want!r}")