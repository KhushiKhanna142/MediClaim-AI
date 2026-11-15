"""Stage 2b (eval venv): DeepEval faithfulness of each claim decision to the policy clauses it cited.

  python3 -m eval.judge_deepeval --pause 4

For every decision the system made, the actual output is the list of policy rules it applied (plain sentences from
eval.judge_export.rule_statements) and the retrieval context is the text of the clauses it cited. Faithfulness = the share of those
rule statements the cited clauses support. This is the plan's "% citations that exist and support the claim".
Citations to clauses with no text in the index are reported separately (they cannot support anything).
Judge = the project's own LLM (same family as the system). Results are cached on disk.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from eval.judge_common import JudgeCore, deepeval_judge, sha256_file  # noqa: E402


def run(rows: list[dict], core: JudgeCore, threshold: float = 0.5) -> dict:
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.test_case import LLMTestCase
    judge = deepeval_judge(core)
    out = {}
    for row in rows:
        base = {"category": row["category"], "decision": row["decision"], "cited": row["cited_clause_ids"],
                "missing_clause_text": row["missing_clause_text"], "unmapped_rules": row["unmapped_rules"]}
        if not row["statements"] or not row["contexts"]:
            out[row["claim_id"]] = {**base, "error": "no statements to check or no clause text found"}
            continue
        try:
            metric = FaithfulnessMetric(threshold=threshold, model=judge, include_reason=True, async_mode=False, verbose_mode=False)
            metric.measure(LLMTestCase(input="Which policy rules justify this claim decision?", actual_output=" ".join(row["statements"]),
                                       retrieval_context=row["contexts"]))
            out[row["claim_id"]] = {**base, "faithfulness": round(float(metric.score), 3), "reason": metric.reason}
        except Exception as exc:  # noqa: BLE001
            out[row["claim_id"]] = {**base, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return out


def summarise(res: dict) -> str:
    ok = [v for v in res.values() if "error" not in v]
    if not ok:
        return "no scored decisions"
    full = sum(1 for v in ok if v["faithfulness"] >= 0.999)
    lines = [f"decisions scored   {len(ok)} of {len(res)}", f"mean faithfulness  {statistics.mean(v['faithfulness'] for v in ok):.3f}",
             f"fully supported    {full}/{len(ok)}"]
    by_cat: dict[str, list[float]] = {}
    for v in ok:
        by_cat.setdefault(v["category"] or "?", []).append(v["faithfulness"])
    lines += [f"  {c:22} n={len(s):<2} mean={statistics.mean(s):.2f}" for c, s in sorted(by_cat.items())]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="eval/results/judge_inputs_groundedness.jsonl")
    ap.add_argument("--out", default="eval/results/deepeval_groundedness.json")
    ap.add_argument("--cache", default="eval/results/judge_cache.json")
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    import deepeval
    from src.llm import get_llm
    rows = [json.loads(l) for l in Path(a.inputs).read_text().splitlines() if l.strip()]
    core = JudgeCore(get_llm(), a.cache, a.pause)
    res = run(rows, core, a.threshold)
    meta = {"input_sha256": sha256_file(a.inputs), "judge_model": str(core.model_name), "deepeval": getattr(deepeval, "__version__", "?"),
            "judge_calls": core.calls, "cache_hits": core.cache_hits}
    Path(a.out).write_text(json.dumps({"meta": meta, "results": res}, indent=1))
    print(f"\ninputs sha256 {meta['input_sha256']}\njudge {meta['judge_model']} · deepeval {meta['deepeval']} · {core.calls} new calls, {core.cache_hits} cached\n\n{summarise(res)}")
    missing = {k: v["missing_clause_text"] for k, v in res.items() if v["missing_clause_text"]}
    if missing:
        print("\ncitations to clauses that do not exist in the index:", missing)
    weak = [(k, v["faithfulness"], v["reason"]) for k, v in res.items() if "error" not in v and v["faithfulness"] < 0.999]
    for k, s, why in weak:
        print(f"\n{k}  faithfulness={s}\n  {why}")
    errs = {k: v["error"] for k, v in res.items() if "error" in v}
    if errs:
        print(f"\n{len(errs)} not scored:", errs)


if __name__ == "__main__":
    main()