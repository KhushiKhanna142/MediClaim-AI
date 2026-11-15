"""Stage 1 (main venv, no new dependencies): run retrieval and collect everything the LLM judges need into two JSONL files.

  python3 -m eval.judge_export --inspect                       # print the shape of a search result and a parent chunk, then stop
  python3 -m eval.judge_export                                 # writes eval/results/judge_inputs_{retrieval,groundedness}.jsonl
  python3 -m eval.judge_export --rewrite                       # retrieve with query rewriting (needs the LLM)

retrieval:     per question (tuned 28 + held-out 10): the top-k retrieved clause texts and the gold clause text -> RAGAS context precision/recall.
groundedness:  per claim decision: the policy rules the system applied, stated as plain sentences, plus the text of the clauses it cited
               -> DeepEval faithfulness ("does the cited clause support the rule that was applied?").
The judges (stage 2) read only these files, so the exact text they score is frozen, hashable and inspectable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

TEXT_KEYS = ("text", "parent_text", "content", "body")
ID_KEYS = ("clause_id", "id", "parent_id")

# One plain-language sentence per policy rule the engine can apply. They describe the RULE, never the claim's own numbers, so a
# faithfulness judge can check them against clause text. Rules not listed here are reported as `unmapped_rules`, never silently dropped.
DEDUCTION_STATEMENTS = (
    ("non_payable", "Non-medical items such as disposables and consumables are not payable."),
    ("sum_insured", "The amount payable cannot exceed the sum insured."),
    ("proportion", "When the room rent exceeds the policy limit, the other related charges are reduced in the same proportion."),
    ("room", "When the room rent exceeds the policy limit, the other related charges are reduced in the same proportion."),
    ("copay", "The insured must bear a fixed percentage of the admissible claim as co-payment."),
    ("co_pay", "The insured must bear a fixed percentage of the admissible claim as co-payment."),
)
STMT_INITIAL_WAIT = "An illness claim made within the initial waiting period after the policy start date is not payable."
STMT_SPECIFIED = "Specified diseases and procedures are not covered until the specified waiting period has been completed."
STMT_PED = "Pre-existing conditions are not covered until the pre-existing disease waiting period has been completed."
STMT_COVERED = "Reasonable expenses of an in-patient hospitalisation are payable up to the sum insured."


def rule_statements(decision: dict) -> tuple[list[str], list[str]]:
    """(statements, unmapped_rule_names) for one system decision. Pure function; see DEDUCTION_STATEMENTS."""
    status = decision.get("decision")
    findings = decision.get("findings") or {}
    out: list[str] = []
    unmapped: list[str] = []
    if status == "reject":
        reasons = " ".join(decision.get("reasons") or []).lower()
        if "initial waiting" in reasons:
            out.append(STMT_INITIAL_WAIT)
        else:
            if findings.get("is_specified"):
                out.append(STMT_SPECIFIED)
            if findings.get("is_pre_existing"):
                out.append(STMT_PED)
            if not out:
                unmapped.append("reject:unknown_reason")
    elif status in ("approve", "partial"):
        out.append(STMT_COVERED)
        for d in decision.get("deductions") or []:
            rule = str(d.get("rule", "")).lower()
            stmt = next((s for key, s in DEDUCTION_STATEMENTS if key in rule), None)
            if stmt is None:
                unmapped.append(rule or "?")
            elif stmt not in out:
                out.append(stmt)
    return out, unmapped


# ------------------------------------------------------------------------------------------------ data access (shape-tolerant)
def _get(obj: Any, keys: Iterable[str]):
    for k in keys:
        v = obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)
        if v:
            return v
    return None


def result_text(r: Any) -> str:
    t = _get(r, TEXT_KEYS)
    if t is None:
        keys = sorted(r) if isinstance(r, dict) else sorted(vars(r))
        raise KeyError(f"cannot find the clause text in a search result; its keys are {keys}. Add the right one to TEXT_KEYS.")
    return t


def build_clause_lookup(parents: Any, base_clause_id) -> dict[tuple[str, str], str]:
    """{(policy_id, base clause id): text}; several parent pieces of one clause are joined."""
    items = parents.values() if isinstance(parents, dict) else parents
    lookup: dict[tuple[str, str], list[str]] = {}
    for p in items:
        if isinstance(p, str):
            raise TypeError("parents hold bare strings; need records with policy_id, clause_id and text. Run with --inspect and share the output.")
        pid, cid, txt = _get(p, ("policy_id", "policy")), _get(p, ID_KEYS), _get(p, TEXT_KEYS)
        if not (pid and cid and txt):
            keys = sorted(p) if isinstance(p, dict) else sorted(vars(p))
            raise KeyError(f"parent record lacks policy_id/clause_id/text; keys are {keys}. Run with --inspect and adjust ID_KEYS/TEXT_KEYS.")
        lookup.setdefault((pid, base_clause_id(cid)), []).append(txt)
    return {k: "\n".join(v) for k, v in lookup.items()}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ------------------------------------------------------------------------------------------------ builders
def retrieval_rows(retr, lookup, questions: list[dict], set_name: str, k: int, rewriter, base_clause_id) -> list[dict]:
    rows = []
    for q in questions:
        extra = rewriter(q["question"]) if rewriter else None
        res = retr.search(q["question"], k=k, policy_ids=[q["policy_id"]] if q.get("policy_id") else None, mode="hybrid_rerank", extra_queries=extra)
        gold = list(q["gold_clause_ids"])
        ref = [lookup.get((q["policy_id"], base_clause_id(g))) for g in gold]
        rows.append({"id": q["id"], "set": set_name, "policy_id": q.get("policy_id"), "question": q["question"],
                     "retrieved_clause_ids": [r["clause_id"] for r in res], "retrieved_contexts": [result_text(r) for r in res],
                     "gold_clause_ids": gold, "reference": "\n".join(x for x in ref if x), "gold_text_missing": [g for g, x in zip(gold, ref) if not x]})
    return rows


def groundedness_rows(preds: dict, claims_dir: Path, lookup, base_clause_id) -> list[dict]:
    rows = []
    for cid, d in sorted(preds.items()):
        if d.get("error") or d.get("decision") not in ("approve", "partial", "reject") or not d.get("cited_clause_ids"):
            continue
        cj = claims_dir / cid / "claim.json"
        meta = json.loads(cj.read_text()) if cj.exists() else {}
        policy = meta.get("policy_id")
        statements, unmapped = rule_statements(d)
        texts, missing = [], []
        for c in d["cited_clause_ids"]:
            t = lookup.get((policy, base_clause_id(c)))
            (texts if t else missing).append(t or c)
        rows.append({"claim_id": cid, "category": meta.get("category"), "policy_id": policy, "decision": d["decision"],
                     "statements": statements, "unmapped_rules": unmapped, "cited_clause_ids": d["cited_clause_ids"],
                     "contexts": texts, "missing_clause_text": missing})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuned", default="data/golden_set/retrieval_questions.jsonl")
    ap.add_argument("--heldout", default="data/golden_set/heldout_questions.jsonl")
    ap.add_argument("--preds", default="eval/results/graph_extracted_predictions.json")
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--out", default="eval/results")
    ap.add_argument("--k", type=int, default=3, help="contexts per question given to the judge (cost grows with k)")
    ap.add_argument("--rewrite", action="store_true")
    ap.add_argument("--path", default="data/qdrant")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()

    from src.rag.index import build_index
    from src.rag.reranker import get_reranker
    from src.rag.retriever import HybridRetriever, base_clause_id
    client, emb, children, parents = build_index(qdrant_path=a.path)
    retr = HybridRetriever(client, emb, children, parents, get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2"))

    if a.inspect:
        q = read_jsonl(Path(a.heldout))[0]
        r = retr.search(q["question"], k=1, policy_ids=[q["policy_id"]], mode="hybrid_rerank")[0]
        p = next(iter(parents.values())) if isinstance(parents, dict) else parents[0]
        show = lambda o: {k: (str(v)[:60] + "…" if len(str(v)) > 60 else v) for k, v in (o if isinstance(o, dict) else vars(o)).items()}
        print("search result :", json.dumps(show(r), indent=1, default=str))
        print("parent record :", json.dumps(show(p), indent=1, default=str) if not isinstance(p, str) else repr(p[:80]))
        print("parents type  :", type(parents).__name__)
        return

    lookup = build_clause_lookup(parents, base_clause_id)
    rewriter = None
    if a.rewrite:
        from src.llm import get_llm
        from src.rag.rewrite import QueryRewriter
        rewriter = QueryRewriter(get_llm())
    out = Path(a.out)
    rows = []
    for name, path in (("tuned", a.tuned), ("heldout", a.heldout)):
        rows += retrieval_rows(retr, lookup, read_jsonl(Path(path)), name, a.k, rewriter, base_clause_id)
    write_jsonl(out / "judge_inputs_retrieval.jsonl", rows)
    bad = [r["id"] for r in rows if r["gold_text_missing"]]
    print(f"retrieval inputs   : {len(rows)} questions  (rewrite={a.rewrite}, k={a.k})" + (f"  WARNING gold text missing for {bad}" if bad else ""))

    preds_path = Path(a.preds)
    if preds_path.exists():
        g = groundedness_rows(json.loads(preds_path.read_text()), Path(a.claims), lookup, base_clause_id)
        write_jsonl(out / "judge_inputs_groundedness.jsonl", g)
        miss = [(r["claim_id"], r["missing_clause_text"]) for r in g if r["missing_clause_text"]]
        unm = sorted({u for r in g for u in r["unmapped_rules"]})
        print(f"groundedness inputs: {len(g)} decisions from {preds_path.name}")
        if miss:
            print("  cited clauses with no text found (these are citations to non-existent clauses):", miss)
        if unm:
            print("  rules with no statement mapping (add to DEDUCTION_STATEMENTS):", unm)
    else:
        print(f"no {preds_path}; run eval.graph_eval or eval.adjudication_eval first to export groundedness inputs")


if __name__ == "__main__":
    main()