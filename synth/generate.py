"""Generate synthetic claim bundles (structured data + ground truth). PDF rendering is a separate step.

CLI (from repo root):  python -m synth.generate [--seed 7] [--out data/synthetic_claims]
Writes <out>/<claim_id>/claim.json, <out>/<claim_id>/ground_truth.json and <out>/manifest.json.
Ground truth always comes from synth.reference.adjudicate (deterministic code), never from an LLM.
"""
from __future__ import annotations

import argparse
import calendar
import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from synth.models import Claim, Condition, LineItem, REQUIRED_DOCS, Schedule, claim_to_dict
from synth.reference import adjudicate
from synth.rules import RULESETS

try:
    from faker import Faker
except ImportError:  # names fall back to a small built-in list
    Faker = None

FALLBACK_NAMES = ["Asha Verma", "Rohan Iyer", "Meera Nair", "Kiran Patil", "Sanjay Gupta", "Pooja Reddy", "Anil Deshmukh",
                  "Neha Kulkarni", "Vikram Singh", "Lata Menon", "Farhan Sheikh", "Divya Joshi", "Arjun Rao", "Sunita Das"]

DESC = {"room": "Room charges", "surgeon": "Surgeon and anaesthetist fees", "ot": "Operation theatre charges",
        "investigation": "Laboratory and radiology investigations", "nursing": "Nursing charges",
        "medicine": "Pharmacy and medicines", "implant": "Implant / prosthesis",
        "consumable": "Disposable consumables and admission kit", "other": "Consultant visits and monitoring"}

_SURG = lambda s, o, i, n, m, imp, c: {"surgeon": s, "ot": o, "investigation": i, "nursing": n, "medicine": m, "implant": imp, "consumable": c}
PROCS = {
    "cataract surgery (phacoemulsification)": dict(kind="illness", specified=True, days=(1, 1),
        costs=_SURG((18000, 30000), (8000, 12000), (2000, 4000), (1000, 2000), (2000, 4000), (9000, 25000), (500, 1500))),
    "inguinal hernia repair": dict(kind="illness", specified=True, days=(2, 3),
        costs=_SURG((30000, 50000), (12000, 20000), (4000, 8000), (3000, 6000), (6000, 12000), (10000, 25000), (1500, 3000))),
    "total knee replacement": dict(kind="illness", specified=True, days=(4, 6),
        costs=_SURG((60000, 90000), (25000, 40000), (8000, 15000), (10000, 18000), (15000, 30000), (120000, 200000), (3000, 6000))),
    "laparoscopic cholecystectomy (gallstones)": dict(kind="illness", specified=True, days=(2, 3),
        costs=_SURG((35000, 55000), (15000, 25000), (5000, 9000), (3000, 6000), (6000, 12000), (0, 0), (2000, 4000))),
    "acute appendicitis, appendectomy": dict(kind="illness", specified=False, days=(3, 4),
        costs=_SURG((30000, 50000), (12000, 20000), (5000, 9000), (4000, 8000), (8000, 14000), (0, 0), (2000, 3500))),
    "dengue fever": dict(kind="illness", specified=False, days=(4, 5),
        costs={"other": (8000, 18000), "investigation": (6000, 12000), "nursing": (4000, 8000), "medicine": (8000, 18000), "consumable": (800, 2000)}),
    "pneumonia": dict(kind="illness", specified=False, days=(4, 6),
        costs={"other": (9000, 20000), "investigation": (6000, 12000), "nursing": (5000, 9000), "medicine": (10000, 22000), "consumable": (900, 2200)}),
    "fracture of femur, ORIF (road accident)": dict(kind="accident", specified=False, days=(4, 6),
        costs=_SURG((50000, 80000), (20000, 35000), (6000, 12000), (6000, 12000), (10000, 20000), (40000, 90000), (2500, 5000))),
    "diabetic foot infection with debridement": dict(kind="illness", specified=False, days=(5, 7),
        costs=_SURG((25000, 40000), (10000, 18000), (6000, 12000), (6000, 11000), (12000, 25000), (0, 0), (1500, 3000))),
}
SPECIFIED = [n for n, p in PROCS.items() if p["specified"]]
PLAIN = ["acute appendicitis, appendectomy", "dengue fever", "pneumonia"]
ACCIDENT = ["fracture of femur, ORIF (road accident)"]
ROOM_RATE = {"shared": (2500, 3500), "standard_single": (4000, 6000), "deluxe": (8000, 12000), "private": (4000, 6000)}

# (category, count per policy)
PLAN = [("clean_approve", 3), ("approve_continuity", 1), ("partial_room", 2), ("partial_nonpayable", 1), ("partial_si_cap", 1), ("reject_specified", 2),
        ("reject_30day", 1), ("reject_ped", 1), ("multi_hop", 1), ("missing_docs", 1), ("total_mismatch", 1)]
EXPECTED_STATUS = {"clean_approve": "approve", "approve_continuity": "approve", "partial_room": "partial",
                   "partial_nonpayable": "partial", "partial_si_cap": "partial", "reject_specified": "reject", "reject_30day": "reject", "reject_ped": "reject",
                   "multi_hop": "reject", "missing_docs": "needs_review", "total_mismatch": "needs_review"}


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.year * 12 + d.month - 1 + m, 12)
    mo += 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def rnd(x: float, step: int = 50) -> int:
    return int(round(x / step) * step)


def build_items(rng, proc, days, room_rate, room_claimed, amplify_implant=1.0, consumables=True):
    items = [LineItem("room", f"Room charges ({room_claimed.replace('_', ' ')})", days, room_rate, days * room_rate)]
    for cat, (lo, hi) in proc["costs"].items():
        if hi == 0 or (cat == "consumable" and not consumables):
            continue
        amt = rnd(rng.uniform(lo, hi) * (amplify_implant if cat == "implant" else 1.0))
        items.append(LineItem(cat, DESC[cat], 1, amt, amt))
    return items


def _person(rng, fake):
    name = fake.name() if fake else rng.choice(FALLBACK_NAMES)
    return {"name": name, "age": rng.randint(28, 72), "sex": rng.choice(["F", "M"])}


def make_claim(rng, fake, policy_id: str, category: str, idx: int) -> Claim:
    si = rng.choice([300000, 500000, 1000000])
    if category in ("clean_approve", "approve_continuity"):
        si = 1000000          # large bills must not hit the sum insured cap in a clean claim
    if policy_id == "niva_aspire":
        ped_m, spec_m = rng.choice([12, 24, 36]), rng.choice([12, 24])
    else:
        ped_m, spec_m = 36, 24
    admission = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
    room_claimed, prior, room_limit, room_mod, eligible = "standard_single", 0, None, False, "standard_single"
    is_ped, docs, mismatch = False, ["claim_form", "hospital_bill", "discharge_summary", "id_proof", "lab_report", "prescription"], 0
    amplify = 1.0

    def clean_months(name):
        p = PROCS[name]
        if p["kind"] == "accident":
            return rng.randint(0, 5)
        return (spec_m + rng.randint(4, 14)) if p["specified"] else rng.randint(3, 30)

    if category in ("clean_approve", "partial_room", "partial_nonpayable", "missing_docs", "total_mismatch"):
        name = rng.choice(SPECIFIED + PLAIN + ACCIDENT)
        months = clean_months(name)
        if category == "partial_room":
            if policy_id == "niva_aspire":
                room_mod = True
                eligible, room_claimed = rng.choice([("shared", "standard_single"), ("shared", "deluxe"), ("standard_single", "deluxe")])
            else:
                si, room_limit, room_claimed = 500000, 5000, "private"
        if category == "missing_docs":
            docs.remove(rng.choice(list(REQUIRED_DOCS)))
        if category == "total_mismatch":
            mismatch = rng.choice([-1, 1]) * rng.randint(5, 50) * 100
    elif category == "approve_continuity":
        name = rng.choice(SPECIFIED)
        months = rng.randint(3, 8)
        prior = spec_m + rng.randint(2, 6)
    elif category == "partial_si_cap":
        name, si, months = "total knee replacement", 300000, spec_m + rng.randint(4, 14)
        amplify = 1.25
    elif category == "reject_specified":
        name, months = rng.choice(SPECIFIED), spec_m - rng.randint(4, 8)
    elif category == "reject_30day":
        name, months = rng.choice(PLAIN), 0
    elif category == "reject_ped":
        name, months, is_ped = "diabetic foot infection with debridement", ped_m - rng.randint(4, 8), True
    elif category == "multi_hop":
        name, is_ped, ped_m, spec_m = "total knee replacement", True, 36, 24
        months = spec_m + rng.randint(4, 6)
    else:
        raise ValueError(category)

    proc = PROCS[name]
    start = admission - timedelta(days=rng.randint(5, 20)) if category == "reject_30day" else add_months(admission, -months)
    days = rng.randint(*proc["days"])
    rate = rnd(rng.uniform(*ROOM_RATE[room_claimed]), 100)
    if category == "partial_room" and policy_id != "niva_aspire":
        rate = rnd(room_limit * rng.uniform(1.4, 1.9), 100)
    for _ in range(30):
        items = build_items(rng, proc, days, rate, room_claimed, amplify,
                            consumables=category not in ("clean_approve", "approve_continuity"))
        gross = sum(i.amount for i in items)
        non_pay = sum(i.amount for i in items if i.category == "consumable")
        if category != "partial_si_cap" or gross - non_pay > si + 15000:
            break
    claim = Claim(
        claim_id=f"C{idx:03d}_{policy_id.split('_')[0]}_{category}", category=category, policy_id=policy_id,
        patient=_person(rng, fake),
        schedule=Schedule(sum_insured=si, policy_start=start, ped_months=ped_m, spec_months=spec_m, room_limit_per_day=room_limit,
                          prior_coverage_months=prior, room_type_modification=room_mod, eligible_room=eligible),
        condition=Condition(name=name, kind=proc["kind"], specified=proc["specified"], is_ped=is_ped),
        admission_date=admission, discharge_date=admission + timedelta(days=days), room_days=days, room_claimed=room_claimed,
        items=items, stated_total=gross + mismatch, docs_present=docs)
    return claim


def generate(seed: int = 7) -> list[tuple[Claim, dict]]:
    rng = random.Random(seed)
    fake = None
    if Faker:
        fake = Faker("en_IN")
        fake.seed_instance(seed)
    out, idx = [], 1
    for policy_id in RULESETS:
        for category, n in PLAN:
            for _ in range(n):
                c = make_claim(rng, fake, policy_id, category, idx)
                out.append((c, adjudicate(c, RULESETS[policy_id])))
                idx += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/synthetic_claims")
    a = ap.parse_args()
    out = Path(a.out)
    claims = generate(a.seed)
    for c, gt in claims:
        d = out / c.claim_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "claim.json").write_text(json.dumps(claim_to_dict(c), indent=1))
        (d / "ground_truth.json").write_text(json.dumps(gt, indent=1))
    manifest = {"seed": a.seed, "claims": len(claims), "by_category": dict(Counter(c.category for c, _ in claims)),
                "by_status": dict(Counter(g["status"] for _, g in claims)), "by_policy": dict(Counter(c.policy_id for c, _ in claims))}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()