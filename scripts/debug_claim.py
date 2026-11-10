"""Show what the policy reader was given and what it concluded for chosen claims. No model calls.

  python scripts/debug_claim.py C009_niva_reject_specified C024_hdfc_reject_specified C001_niva_clean_approve
Reads eval/results/adjudication_oracle_predictions.json for the saved findings, and rebuilds retrieval to print the
passages shown for the 'specified' and 'coverage' topics.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adjudication.reader import gather, passage
from src.rag.index import build_index
from src.rag.reranker import get_reranker
from src.rag.retriever import HybridRetriever
from synth.to_extracted import oracle_extraction

preds = json.loads(Path("eval/results/adjudication_oracle_predictions.json").read_text())
client, emb, children, parents = build_index(qdrant_path="data/qdrant")
retr = HybridRetriever(client, emb, children, parents, get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2"))
for cid in sys.argv[1:]:
    claim = json.loads(Path(f"data/synthetic_claims/{cid}/claim.json").read_text())
    truth = json.loads(Path(f"data/synthetic_claims/{cid}/ground_truth.json").read_text())
    p = preds[cid]
    f = p.get("findings", {})
    print("=" * 100)
    print(cid, "| diagnosis:", claim["condition"]["name"], "| truth specified:", claim["condition"]["specified"])
    print("expected :", truth["status"], truth["expected_clause_ids"])
    print("got      :", p["decision"], p["cited_clause_ids"])
    print("is_specified:", f.get("is_specified"), "| spec_clause:", f.get("spec_clause"), "| coverage_clause:", f.get("coverage_clause"))
    print("reasoning:", f.get("reasoning"))
    ev = gather(retr, oracle_extraction(claim), claim["policy_id"])
    for topic in ("specified", "coverage"):
        print(f"\n--- passages shown for topic '{topic}' ---")
        for h in ev[topic]:
            print(f"[{h['clause_id']}] {passage(h)[:1500]}\n")