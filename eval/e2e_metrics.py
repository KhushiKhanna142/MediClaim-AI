"""Scoring for end-to-end claim decisions. Pure functions, no model calls."""
from __future__ import annotations

from collections import defaultdict

from src.rag.retriever import base_clause_id

PAYABLE_TOL = 1.0   # rupees


def cite_key(clause_id: str) -> str:
    """Citations match at clause level: a sub-item such as 2.13/1 counts as a citation of clause 2.13."""
    return base_clause_id(clause_id).split("/")[0]


def score_claim(pred: dict, truth: dict) -> dict:
    status = truth["status"]
    decision_ok = pred.get("decision") == status
    claimed = float(truth["claimed_amount"]) or 1.0
    scored_money = status != "needs_review"
    pay_pred = pred.get("payable_amount")
    if pay_pred is None:
        pay_pred = 0.0
    err = abs(float(pay_pred) - float(truth["payable_amount"])) if scored_money else None
    exp = {cite_key(c) for c in truth.get("expected_clause_ids", [])}
    got = {cite_key(c) for c in pred.get("cited_clause_ids", [])}
    retrieved = {cite_key(c) for c in pred.get("retrieved_clause_ids", [])}
    truth_pay = float(truth.get("payable_amount") or 0.0)
    overpay = float(pay_pred) - truth_pay > PAYABLE_TOL   # paid more than the correct amount: the costly kind of error
    return {
        "decision_ok": decision_ok,
        "overpay": overpay,
        "payable_exact": (err <= PAYABLE_TOL) if scored_money else None,
        "payable_err_pct": (err / claimed * 100) if scored_money else None,
        "cite_recall": (len(exp & got) / len(exp)) if exp else None,
        "cite_precision": (len(exp & got) / len(got)) if got and exp else (0.0 if exp else None),
        "cite_unsupported": (len(got - retrieved) / len(got)) if got and retrieved else None,
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def aggregate(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "decision_acc": _mean([float(r["decision_ok"]) for r in rows]),
        "payable_exact": _mean([None if r["payable_exact"] is None else float(r["payable_exact"]) for r in rows]),
        "payable_err_pct": _mean([r["payable_err_pct"] for r in rows]),
        "overpay_rate": _mean([float(r["overpay"]) for r in rows]),
        "cite_recall": _mean([r["cite_recall"] for r in rows]),
        "cite_precision": _mean([r["cite_precision"] for r in rows]),
        "cite_unsupported": _mean([r["cite_unsupported"] for r in rows]),
    }


def by_category(scored: list[tuple[str, dict]]) -> dict:
    groups = defaultdict(list)
    for cat, row in scored:
        groups[cat].append(row)
    return {c: aggregate(r) for c, r in sorted(groups.items())}


def format_table(overall: dict, cats: dict) -> str:
    cols = ["n", "decision_acc", "payable_exact", "payable_err_pct", "overpay_rate", "cite_recall", "cite_precision", "cite_unsupported"]
    head = f"{'category':20}" + "".join(f"{c:>15}" for c in cols)
    lines = [head]
    for name, m in list(cats.items()) + [("ALL", overall)]:
        vals = "".join(f"{m['n']:>15d}" if c == "n" else f"{m[c]:>15.2f}" for c in cols)
        lines.append(f"{name:20}{vals}")
    return "\n".join(lines)