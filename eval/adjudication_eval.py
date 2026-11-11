"""Run validation + policy reading + decision engine over the synthetic claims and score with the same metrics as the baseline.

  python3 -m eval.adjudication_eval --input oracle      # perfect extraction: measures the reasoning stages alone
  python3 -m eval.adjudication_eval --input extracted   # uses eval/results/extraction_predictions.json (run extraction_eval first)
Add --pause 8 for free-tier limits. Failed claims are retried on the next run; --score-only rescored saved results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from eval.e2e_eval import report
from src.extraction.schemas import ExtractedClaim

RESULTS = Path("eval/results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", choices=["oracle", "extracted"], default="oracle")
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--path", default="data/qdrant")
    a = ap.parse_args()
    dirs = sorted(p for p in Path(a.claims).glob("C*/") if (p / "ground_truth.json").exists())[: a.limit]
    pred_path = RESULTS / f"adjudication_{a.input}_predictions.json"
    preds = json.loads(pred_path.read_text()) if pred_path.exists() else {}
    if not a.score_only:
        from src.adjudication.pipeline import Adjudicator
        from src.llm import get_llm
        from src.rag.index import build_index
        from src.rag.reranker import get_reranker
        from src.rag.retriever import HybridRetriever
        from synth.to_extracted import oracle_extraction
        client, emb, children, parents = build_index(qdrant_path=a.path)
        adj = Adjudicator(HybridRetriever(client, emb, children, parents, get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2")), get_llm())
        extracted = json.loads(Path("eval/results/extraction_predictions.json").read_text()) if a.input == "extracted" else {}
        quota = 0
        for d in dirs:
            cid = d.name
            # fingerprint of the extraction this result is based on; a re-run extraction invalidates the cached result
            sig = hashlib.sha1(json.dumps(extracted[cid], sort_keys=True).encode()).hexdigest()[:12] if cid in extracted else None
            if cid in preds and not preds[cid].get("error") and preds[cid].get("_sig") == sig:
                continue
            claim = json.loads((d / "claim.json").read_text())
            try:
                if a.input == "oracle":
                    c, docs = oracle_extraction(claim), claim["docs_present"]
                else:
                    if cid not in extracted or "error" in extracted[cid]:
                        print(f"  {cid:36} skipped (no extraction result)")
                        continue
                    from src.validation.checks import docs_in_dir
                    c, docs = ExtractedClaim.model_validate(extracted[cid]), docs_in_dir(d)
                preds[cid] = adj.run(c, claim["policy_id"], docs)
                preds[cid]["_sig"] = sig
                quota = 0
                p = preds[cid]
                print(f"  {cid:36} -> {p['decision']}" + (f"  (dropped citations: {p['dropped_citations']})" if p.get("dropped_citations") else ""))
            except Exception as e:  # noqa: BLE001
                preds[cid] = {"decision": None, "payable_amount": None, "cited_clause_ids": [], "error": repr(e)}
                quota = quota + 1 if "429" in repr(e) else 0
                print(f"  {cid:36} FAILED: {repr(e)[:160]}")
            RESULTS.mkdir(parents=True, exist_ok=True)
            pred_path.write_text(json.dumps(preds, indent=1))
            if quota >= 2:
                print("\nStopping: API quota used up. Rerun later; finished claims are kept.")
                break
            time.sleep(a.pause)
    table = report(dirs, preds)
    (RESULTS / f"adjudication_{a.input}_report.txt").write_text(table)
    print("\n" + table)


if __name__ == "__main__":
    main()