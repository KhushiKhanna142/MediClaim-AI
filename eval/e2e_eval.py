"""Run a pipeline over the synthetic claims and score it against ground truth.

  python -m eval.e2e_eval --system naive            # needs an LLM key (GEMINI_API_KEY etc.) and Tesseract
  python -m eval.e2e_eval --system naive --limit 5  # quick smoke run
  python -m eval.e2e_eval --system naive --score-only   # rescore saved predictions, no API calls

Predictions are saved to eval/results/<system>_predictions.json after every claim, so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from eval.e2e_metrics import aggregate, by_category, format_table, score_claim

RESULTS = Path("eval/results")


def load_claims(root: Path, limit: int | None = None):
    dirs = sorted(p for p in root.glob("C*/") if (p / "ground_truth.json").exists())
    return dirs[:limit] if limit else dirs


def run(system, claim_dirs: list[Path], pred_path: Path, score_only: bool = False, pause: float = 0.0) -> dict:
    preds = json.loads(pred_path.read_text()) if pred_path.exists() else {}
    quota_fails = 0
    for d in claim_dirs:
        truth = json.loads((d / "ground_truth.json").read_text())
        cid = truth["claim_id"]
        if score_only or (cid in preds and not preds[cid].get("error")):
            continue   # failed predictions are retried on the next run
        try:
            preds[cid] = system.predict(d, truth["policy_id"])
        except Exception as e:  # noqa: BLE001 - one bad claim should not stop the run
            preds[cid] = {"decision": None, "payable_amount": None, "cited_clause_ids": [], "error": repr(e)}
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        pred_path.write_text(json.dumps(preds, indent=1))
        p = preds[cid]
        print(f"  {cid:36} -> {p.get('decision')}" + (f"   FAILED: {p['error'][:150]}" if p.get("error") else ""))
        if p.get("error") and p.get("raw_reply") is not None:
            print(f"      raw reply: {p['raw_reply'][:200]!r}")
        quota_fails = quota_fails + 1 if "429" in str(p.get("error", "")) else 0
        if quota_fails >= 2:
            print("\nStopping: the API quota is used up. Wait a while (daily limits reset overnight Pacific time) and rerun; finished claims are kept.")
            break
        time.sleep(pause)
    return preds


def report(claim_dirs, preds) -> str:
    scored, cats, failed = [], [], 0
    for d in claim_dirs:
        truth = json.loads((d / "ground_truth.json").read_text())
        p = preds.get(truth["claim_id"])
        if p is None:
            continue
        if p.get("error"):
            failed += 1      # a failed run is not a wrong answer; keep it out of the scores
            continue
        row = score_claim(preds[truth["claim_id"]], truth)
        scored.append(row)
        cats.append((truth["category"], row))
    note = f"\n\n{failed} claim(s) failed to produce a decision and are excluded; rerun to retry them." if failed else ""
    return format_table(aggregate(scored), by_category(cats)) + note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="naive", choices=["naive"])
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--path", default="data/qdrant")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds to wait between claims, helps with free-tier rate limits")
    a = ap.parse_args()
    dirs = load_claims(Path(a.claims), a.limit)
    system = None
    if not a.score_only:
        from src.baseline.naive import NaiveBaseline
        from src.llm import get_llm
        from src.rag.index import build_index
        from src.rag.retriever import HybridRetriever
        client, emb, children, parents = build_index(qdrant_path=a.path)
        system = NaiveBaseline(HybridRetriever(client, emb, children, parents, None), get_llm())
    name = "naive_baseline"
    preds = run(system, dirs, RESULTS / f"{name}_predictions.json", a.score_only, a.pause)
    table = report(dirs, preds)
    (RESULTS / f"{name}_report.txt").write_text(table)
    print("\n" + table)


if __name__ == "__main__":
    main()