"""Run every synthetic claim through the full LangGraph workflow and score the system's recommendation with the same
metrics as adjudication_eval, plus workflow metrics (escalation rate, verifier outcomes).

  python3 -m eval.graph_eval --input oracle      # perfect extraction
  python3 -m eval.graph_eval --input extracted   # uses eval/results/extraction_predictions.json
Add --pause 8 for free-tier limits, --no-critic to skip the verifier's LLM call (code checks still run).
Humans are not simulated: a claim that escalates is scored on the recommendation the system made before escalating.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from eval.e2e_eval import report
from src.validation.checks import docs_in_dir

RESULTS = Path("eval/results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", choices=["oracle", "extracted"], default="oracle")
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--no-critic", action="store_true")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--path", default="data/qdrant")
    a = ap.parse_args()
    dirs = sorted(p for p in Path(a.claims).glob("C*/") if (p / "ground_truth.json").exists())[: a.limit]
    pred_path = RESULTS / f"graph_{a.input}_predictions.json"
    preds = json.loads(pred_path.read_text()) if pred_path.exists() else {}
    if not a.score_only:
        from src.adjudication.reader import PolicyReader
        from src.agents.verifier import Verifier
        from src.graph.workflow import build_graph, run_claim
        from src.llm import get_llm
        from src.rag.index import build_index
        from src.rag.reranker import get_reranker
        from src.rag.retriever import HybridRetriever
        from synth.to_extracted import oracle_extraction
        llm = get_llm()
        client, emb, children, parents = build_index(qdrant_path=a.path)
        retriever = HybridRetriever(client, emb, children, parents, get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2"))
        graph = build_graph(reader=PolicyReader(retriever, llm), verifier=Verifier(None if a.no_critic else llm))
        extracted = json.loads(Path("eval/results/extraction_predictions.json").read_text()) if a.input == "extracted" else {}
        quota = 0
        for d in dirs:
            cid = d.name
            sig = hashlib.sha1(json.dumps([extracted.get(cid), a.no_critic], sort_keys=True).encode()).hexdigest()[:12]
            if cid in preds and not preds[cid].get("error") and preds[cid].get("_sig") == sig:
                continue
            claim = json.loads((d / "claim.json").read_text())
            try:
                if a.input == "oracle":
                    inp = {"extracted": oracle_extraction(claim).model_dump(mode="json"), "docs_present": claim["docs_present"]}
                else:
                    if cid not in extracted or "error" in extracted[cid]:
                        print(f"  {cid:36} skipped (no extraction result)")
                        continue
                    inp = {"extracted": extracted[cid], "docs_present": docs_in_dir(d)}
                res = run_claim(graph, {"policy_id": claim["policy_id"], **inp}, f"{a.input}-{cid}")
                st = res["state"]
                preds[cid] = {**st["decision"], "_sig": sig, "escalated": res["status"] == "awaiting_human",
                              "escalation_reasons": st.get("escalation_reasons", []), "verifier": st.get("verifier"),
                              "read_attempts": (st.get("retries") or {}).get("read_policy", 0)}
                quota = 0
                p = preds[cid]
                print(f"  {cid:36} -> {p['decision']:13}" + ("  ESCALATED " + ",".join(p["escalation_reasons"]) if p["escalated"] else ""))
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
    done = {k: v for k, v in preds.items() if not v.get("error")}
    esc = Counter(r for v in done.values() for r in v.get("escalation_reasons", []))
    summary = (f"\nworkflow: {len(done)} claims | escalated {sum(v['escalated'] for v in done.values())} "
               f"| verifier failed {sum(1 for v in done.values() if v.get('verifier') and not v['verifier']['passed'])} "
               f"| re-read policy {sum(1 for v in done.values() if v.get('read_attempts', 0) > 1)}\n"
               f"escalation reasons: {dict(esc)}")
    table = report(dirs, preds)
    (RESULTS / f"graph_{a.input}_report.txt").write_text(table + summary)
    print("\n" + table + summary)


if __name__ == "__main__":
    main()