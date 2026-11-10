"""Score the extraction stage against claim.json.  python3 -m eval.extraction_eval [--limit 5] [--pause 8] [--score-only]

Reads the rendered PDFs (OCR where scanned), extracts, and compares field by field. Results are cached in
eval/results/extraction_predictions.json so reruns only call the model for claims that are missing or failed.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.extraction.schemas import ExtractedClaim

CACHE = Path("eval/results/extraction_predictions.json")

SCALARS = [  # (name, getter on truth claim.json)
    ("patient_name", lambda c: c["patient"]["name"]), ("age", lambda c: c["patient"]["age"]), ("sex", lambda c: c["patient"]["sex"]),
    ("diagnosis", lambda c: c["condition"]["name"]),
    ("cause", lambda c: "accident" if c["condition"]["kind"] == "accident" else "illness"),
    ("admission_date", lambda c: c["admission_date"]), ("discharge_date", lambda c: c["discharge_date"]),
    ("room_category_claimed", lambda c: c["room_claimed"]), ("claimed_total", lambda c: c["stated_total"]),
    ("bill_total", lambda c: c["stated_total"]),
    ("sum_insured", lambda c: c["schedule"]["sum_insured"]), ("policy_start", lambda c: c["schedule"]["policy_start"]),
    ("ped_waiting_months", lambda c: c["schedule"]["ped_months"]), ("specified_waiting_months", lambda c: c["schedule"]["spec_months"]),
    ("room_limit_per_day", lambda c: c["schedule"]["room_limit_per_day"]), ("copay_pct", lambda c: c["schedule"]["copay_pct"]),
    ("continuity_credit_months", lambda c: c["schedule"]["prior_coverage_months"]),
    ("room_type_modification", lambda c: c["schedule"]["room_type_modification"]),
    ("eligible_room", lambda c: c["schedule"]["eligible_room"]),
]


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else (v.isoformat() if hasattr(v, "isoformat") else v)


def score_extraction(pred: dict, truth: dict) -> dict:
    """pred is ExtractedClaim.model_dump(); returns per-field booleans plus item metrics.
    Claims with a deliberate total mismatch keep bill_total/claimed_total checks, since the form and bill totals are
    both generated from stated_total."""
    out = {name: _norm(pred.get(name)) == _norm(get(truth)) for name, get in SCALARS}
    t_items = truth["items"]
    p_items = list(pred.get("items", []))
    used, matched, cat_ok = set(), 0, 0
    for ti in t_items:
        for j, pi in enumerate(p_items):
            if j not in used and pi["amount"] == ti["amount"] and pi["qty"] == ti["qty"]:
                used.add(j)
                matched += 1
                cat_ok += pi["category"] == ti["category"]
                break
    out["item_recall"] = matched / len(t_items) if t_items else 1.0
    out["item_category_acc"] = cat_ok / matched if matched else 0.0
    out["no_extra_items"] = len(p_items) == len(t_items)
    return out


def summarize(rows: list[dict]) -> dict:
    keys = rows[0].keys()
    return {k: sum(float(r[k]) for r in rows) / len(rows) for k in keys}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    dirs = sorted(p for p in Path(a.claims).glob("C*/") if (p / "claim.json").exists())[: a.limit]
    preds = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if not a.score_only:
        from src.extraction.extract import Extractor
        from src.llm import get_llm
        ex = Extractor(get_llm())
        quota = 0
        for d in dirs:
            cid = d.name
            if cid in preds and "error" not in preds[cid]:
                continue
            try:
                preds[cid] = json.loads(ex.extract_dir(d).model_dump_json())
                quota = 0
                print(f"  {cid:36} ok")
            except Exception as e:  # noqa: BLE001
                preds[cid] = {"error": repr(e)}
                quota = quota + 1 if "429" in repr(e) else 0
                print(f"  {cid:36} FAILED: {repr(e)[:160]}")
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(preds, indent=1))
            if quota >= 2:
                print("\nStopping: API quota used up. Rerun later; finished claims are kept.")
                break
            time.sleep(a.pause)
    rows, failed = [], 0
    for d in dirs:
        p = preds.get(d.name)
        if p is None:
            continue
        if "error" in p:
            failed += 1
            continue
        rows.append(score_extraction(p, json.loads((d / "claim.json").read_text())))
    if not rows:
        print("nothing to score")
        return
    s = summarize(rows)
    print(f"\n{len(rows)} claims scored" + (f", {failed} failed and excluded" if failed else ""))
    for k, v in s.items():
        print(f"  {k:28} {v:.2f}")


if __name__ == "__main__":
    main()