"""Stage 2a (eval venv): RAGAS context precision and context recall for retrieval, on the tuned 28 and the held-out 10.

  python3 -m eval.judge_ragas --pause 4

Context precision: of the retrieved clauses, are the relevant ones ranked first (judged against the gold clause text).
Context recall:    is everything in the gold clause text supported by what was retrieved.
These complement the ID-based recall@k / MRR in eval.retrieval_eval: they judge the clause *text*, not just its ID.
Judge = the project's own LLM (same family as the system, so read scores with that bias in mind). Results are cached on disk.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path

from eval.judge_common import JudgeCore, ragas_judge, sha256_file


def run(rows: list[dict], core: JudgeCore) -> dict:
    from ragas.metrics.collections import ContextPrecision, ContextRecall
    judge = ragas_judge(core)
    precision, recall = ContextPrecision(llm=judge), ContextRecall(llm=judge)

    async def one(row):
        kw = dict(user_input=row["question"], retrieved_contexts=row["retrieved_contexts"], reference=row["reference"])
        p = await precision.ascore(**kw)
        r = await recall.ascore(**kw)
        return float(p.value), float(r.value)

    out = {}
    for row in rows:
        if not row["reference"] or not row["retrieved_contexts"]:
            out[row["id"]] = {"set": row["set"], "error": "no gold text or no retrieved contexts"}
            continue
        try:
            p, r = asyncio.run(one(row))
            out[row["id"]] = {"set": row["set"], "policy_id": row["policy_id"], "context_precision": round(p, 3), "context_recall": round(r, 3),
                              "gold": row["gold_clause_ids"], "retrieved": row["retrieved_clause_ids"]}
        except Exception as exc:  # noqa: BLE001 - keep going; failed rows are retried next run (judge answers are cached)
            out[row["id"]] = {"set": row["set"], "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return out


def summarise(res: dict) -> str:
    lines = [f"{'set':9} {'n':>3} {'ok':>3} {'ctx precision':>14} {'ctx recall':>11} {'recall=1.0':>11}"]
    for s in ("tuned", "heldout"):
        sub = [v for v in res.values() if v["set"] == s]
        ok = [v for v in sub if "error" not in v]
        if not sub:
            continue
        mp = statistics.mean(v["context_precision"] for v in ok) if ok else float("nan")
        mr = statistics.mean(v["context_recall"] for v in ok) if ok else float("nan")
        full = sum(1 for v in ok if v["context_recall"] >= 0.999)
        lines.append(f"{s:9} {len(sub):>3} {len(ok):>3} {mp:>14.3f} {mr:>11.3f} {full:>8}/{len(ok)}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="eval/results/judge_inputs_retrieval.jsonl")
    ap.add_argument("--out", default="eval/results/ragas_retrieval.json")
    ap.add_argument("--cache", default="eval/results/judge_cache.json")
    ap.add_argument("--pause", type=float, default=0.0)
    a = ap.parse_args()
    import ragas
    from src.llm import get_llm
    rows = [json.loads(l) for l in Path(a.inputs).read_text().splitlines() if l.strip()]
    core = JudgeCore(get_llm(), a.cache, a.pause)
    res = run(rows, core)
    meta = {"input_sha256": sha256_file(a.inputs), "judge_model": str(core.model_name), "ragas": ragas.__version__,
            "judge_calls": core.calls, "cache_hits": core.cache_hits}
    Path(a.out).write_text(json.dumps({"meta": meta, "results": res}, indent=1))
    table = summarise(res)
    print(f"\ninputs sha256 {meta['input_sha256']}\njudge {meta['judge_model']} · ragas {meta['ragas']} · {core.calls} new calls, {core.cache_hits} cached\n\n{table}")
    errs = {k: v["error"] for k, v in res.items() if "error" in v}
    if errs:
        print(f"\n{len(errs)} rows failed (rerun to retry; finished judge calls are cached):")
        for k, v in list(errs.items())[:5]:
            print(f"  {k}: {v}")
    low = [(k, v["context_recall"]) for k, v in res.items() if "error" not in v and v["context_recall"] < 1.0]
    if low:
        print("\ncontext recall below 1.0:", ", ".join(f"{k} ({r})" for k, r in low))


if __name__ == "__main__":
    main()