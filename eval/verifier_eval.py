"""Empirical evaluation of Verifier agent via defect injection.

Tests the verifier's ability to catch critical adjudication errors:
1. Missed Pre-Existing Condition (PED)
2. Missed Room Cap / Proportionate Deduction
3. Missing Supporting Citations
4. Hallucinated / Unretrieved Citations
5. Overpay / Arithmetic Violation
6. Clean claims (False positive rate)
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from src.adjudication.engine import decide
from src.adjudication.findings import Findings
from src.agents.verifier import Verifier
from synth.rules import RULESETS
from synth.to_extracted import oracle_extraction, oracle_findings


PARAPHRASED_PED_HISTORIES = [
    "Patient has been diabetic since 2019, on regular insulin therapy.",
    "h/o chronic kidney disease, on regular medications.",
    "Long-standing hypertension and CAD for 5 years.",
    "Under treatment for lumbar disc herniation since Jan 2021.",
    "Suffering from osteoarthritis of bilateral knees for 4 years.",
    "Past history of bronchial asthma on inhalers.",
    "Patient known to have gallstones since 2020.",
    "Known diabetic and hypertensive, on oral hypoglycemics for 3 years.",
    "History of recurrent renal calculi, previously treated in 2021.",
    "Under medication for rheumatoid arthritis for 36 months.",
    "h/o coronary artery disease with prior stent in 2022.",
    "Suffering from chronic obstructive pulmonary disease since 2018.",
    "Patient has had benign prostatic hyperplasia for 2 years.",
    "Past history of varicose veins of lower limbs, symptomatic for 3 years.",
    "Known to have chronic liver disease, followed up since 2021.",
    "h/o glaucoma in both eyes, on eye drops for 4 years.",
    "Under regular treatment for ankylosing spondylitis since 2020.",
    "Suffering from chronic sinusitis and nasal polyps for 2 years.",
    "Past medical history of inflammatory bowel disease since 2019.",
    "Patient on regular medication for chronic pancreatitis for 3 years.",
]

UNRELATED_CLEAN_HISTORIES = [
    "h/o mild hypertension, well controlled on amlodipine.",
    "Childhood history of asthma, no active episodes in 15 years.",
    "Past history of treated typhoid fever 5 years ago, recovered completely.",
    "Known hypertensive for 2 years, well managed on monotherapy.",
    "h/o seasonal allergic rhinitis on PRN antihistamines.",
    "Past history of appendectomy 10 years ago, uneventful recovery.",
    "h/o treated malaria in 2019, fully resolved.",
    "Mild dyslipidemia managed with diet and lifestyle modifications.",
    "Past history of uncomplicated dengue fever in 2021.",
    "History of minor wrist sprain 3 years ago, healed normally.",
]
def load_dev_claims():
    claims = []
    for d in sorted(Path("data/synthetic_claims").glob("C*/")):
        claim_data = json.loads((d / "claim.json").read_text())
        policy_id = claim_data["policy_id"]
        rules = RULESETS[policy_id]
        c = oracle_extraction(claim_data)
        f = oracle_findings(claim_data, rules)
        retrieved_ids = [rules.coverage_clause, rules.wait30_clause,
                         rules.spec_clause, rules.ped_clause,
                         rules.ped_def_clause, rules.room_cap_clause,
                         rules.room_mod_clause, rules.copay_clause,
                         rules.nonpayable_clause, rules.sum_insured_clause]
        retrieved_ids = [x for x in retrieved_ids if x]
        claims.append({"cid": d.name, "claim": c, "findings": f, "rules": rules,
                       "retrieved_ids": retrieved_ids, "raw": claim_data})
    return claims


def run_injection_suite(v: Verifier):
    claims = load_dev_claims()
    results = {}

    # 1. Clean claims (Negative Control: expect passed=True)
    clean_passed = 0
    clean_total = 0
    for item in claims:
        c, f, r_ids = item["claim"], item["findings"], item["retrieved_ids"]
        dec = decide(c, f)
        res = v.verify(c, f.model_dump(), dec, r_ids)
        if res.passed:
            clean_passed += 1
        clean_total += 1
    results["clean_claims"] = {
        "total": clean_total,
        "caught": clean_total - clean_passed,  # false positives
        "rate": clean_passed / clean_total if clean_total else 0.0,
        "label": "Pass Rate (Negative Control)",
    }

    # 2. Missed PED: claims with PED where findings drop is_pre_existing
    ped_caught, ped_total = 0, 0
    for item in claims:
        if item["raw"]["condition"]["is_ped"]:
            c, r_ids = item["claim"], item["findings"]
            # inject defect: reader missed PED
            f_injected = copy.deepcopy(item["findings"])
            f_injected.is_pre_existing = False
            f_injected.ped_clause = None
            dec = decide(c, f_injected)
            res = v.verify(c, f_injected.model_dump(), dec, item["retrieved_ids"])
            if not res.passed:
                ped_caught += 1
            ped_total += 1
    results["missed_ped"] = {
        "total": ped_total,
        "caught": ped_caught,
        "rate": ped_caught / ped_total if ped_total else 0.0,
        "label": "Catch Rate: Synthetic PED (n=4)",
    }

    # 2b. Paraphrased PED: 20 clinical histories with NO trigger words and NO onset date
    para_caught, para_total = 0, len(PARAPHRASED_PED_HISTORIES)
    ped_claim_item = next(item for item in claims if item["raw"]["condition"]["is_ped"])
    for para in PARAPHRASED_PED_HISTORIES:
        c_copy = copy.deepcopy(ped_claim_item["claim"])
        c_copy.known_history = para
        c_copy.history_onset_date = None  # test text phrasing alone, without explicit onset date
        f_injected = copy.deepcopy(ped_claim_item["findings"])
        f_injected.is_pre_existing = False
        f_injected.ped_clause = None
        dec = decide(c_copy, f_injected)
        res = v.verify(c_copy, f_injected.model_dump(), dec, ped_claim_item["retrieved_ids"])
        if not res.passed:
            para_caught += 1
    results["paraphrased_ped"] = {
        "total": para_total,
        "caught": para_caught,
        "rate": para_caught / para_total if para_total else 0.0,
        "label": "Catch Rate: Paraphrased PED (n=20)",
    }

    # 1b. Clean Claims with Unrelated History: testing False-Positive Rate on unrelated conditions
    unrel_escalated, unrel_total = 0, len(UNRELATED_CLEAN_HISTORIES)
    clean_items = [item for item in claims if item["raw"]["category"] in ("clean_approve", "partial_room")]
    for i, unrel_hist in enumerate(UNRELATED_CLEAN_HISTORIES):
        target = clean_items[i % len(clean_items)]
        c_copy = copy.deepcopy(target["claim"])
        c_copy.known_history = unrel_hist
        c_copy.history_onset_date = None
        f = copy.deepcopy(target["findings"])
        dec = decide(c_copy, f)
        res = v.verify(c_copy, f.model_dump(), dec, target["retrieved_ids"])
        if not res.passed:
            unrel_escalated += 1
    results["unrelated_clean"] = {
        "total": unrel_total,
        "caught": unrel_escalated,  # escalated = false positive
        "rate": unrel_escalated / unrel_total if unrel_total else 0.0,
        "label": "False Positive Rate: Unrelated History (n=10)",
    }

    # 3. Missed Room Cap: claims with room rent breach where proportionate deduction was omitted
    room_caught, room_total = 0, 0
    for item in claims:
        c = item["claim"]
        days = max((c.discharge_date - c.admission_date).days, 1)
        room_amt = sum(i.amount for i in c.items if i.category in ("room", "icu"))
        if c.room_limit_per_day and room_amt / days > c.room_limit_per_day + 1.0:
            f_injected = copy.deepcopy(item["findings"])
            f_injected.room_cap_clause = None
            dec = decide(c, f_injected)
            # drop the proportionate deduction from deductions
            dec["deductions"] = [d for d in dec.get("deductions", []) if "proportion" not in d.get("rule", "").lower() and "room" not in d.get("rule", "").lower()]
            dec["payable_amount"] = sum(i.amount for i in c.items) - sum(d.get("amount", 0) for d in dec["deductions"])
            res = v.verify(c, f_injected.model_dump(), dec, item["retrieved_ids"])
            if not res.passed:
                room_caught += 1
            room_total += 1
    results["missed_room_cap"] = {
        "total": room_total,
        "caught": room_caught,
        "rate": room_caught / room_total if room_total else 0.0,
        "label": "Catch Rate on Missed Room Cap",
    }

    # 4. Missing Citation: drop citations from decision
    cite_caught, cite_total = 0, 0
    for item in claims:
        c, f, r_ids = item["claim"], item["findings"], item["retrieved_ids"]
        dec = decide(c, f)
        if dec.get("decision") in ("approve", "partial"):
            dec["cited_clause_ids"] = []
            res = v.verify(c, f.model_dump(), dec, r_ids)
            if not res.passed:
                cite_caught += 1
            cite_total += 1
    results["missing_citations"] = {
        "total": cite_total,
        "caught": cite_caught,
        "rate": cite_caught / cite_total if cite_total else 0.0,
        "label": "Catch Rate on Missing Citations",
    }

    # 5. Hallucinated / Unretrieved Citations
    halluc_caught, halluc_total = 0, 0
    for item in claims:
        c, f, r_ids = item["claim"], item["findings"], item["retrieved_ids"]
        dec = decide(c, f)
        if dec.get("decision") in ("approve", "partial"):
            dec["cited_clause_ids"] = list(dec.get("cited_clause_ids", [])) + ["99.99.HallucinatedClause"]
            res = v.verify(c, f.model_dump(), dec, r_ids)
            if not res.passed:
                halluc_caught += 1
            halluc_total += 1
    results["unretrieved_citations"] = {
        "total": halluc_total,
        "caught": halluc_caught,
        "rate": halluc_caught / halluc_total if halluc_total else 0.0,
        "label": "Catch Rate on Hallucinated Citations",
    }

    # 6. Overpay / Arithmetic Violation: inflate payable amount
    math_caught, math_total = 0, 0
    for item in claims:
        c, f, r_ids = item["claim"], item["findings"], item["retrieved_ids"]
        dec = decide(c, f)
        if dec.get("decision") in ("approve", "partial"):
            dec["payable_amount"] = dec.get("payable_amount", 0) + (c.sum_insured or 100000) + 50000
            res = v.verify(c, f.model_dump(), dec, r_ids)
            if not res.passed:
                math_caught += 1
            math_total += 1
    results["overpay_math"] = {
        "total": math_total,
        "caught": math_caught,
        "rate": math_caught / math_total if math_total else 0.0,
        "label": "Catch Rate on Overpay / Math Cap",
    }

    return results


def print_results(title: str, results: dict):
    print(f"\n=== {title} ===")
    print(f"{'Category':45} {'Result/Total':14} {'Rate':8}")
    print("-" * 70)
    for cat, data in results.items():
        if cat == "clean_claims":
            print(f"{data['label']:45} {data['total'] - data['caught']}/{data['total']:<12} {data['rate']*100:6.1f}%")
        elif cat == "unrelated_clean":
            print(f"{data['label']:45} {data['caught']}/{data['total']:<12} {data['rate']*100:6.1f}%")
        else:
            print(f"{data['label']:45} {data['caught']}/{data['total']:<12} {data['rate']*100:6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-critic", action="store_true", help="run with LLM critic")
    a = ap.parse_args()

    v_code = Verifier(llm=None)
    res_code = run_injection_suite(v_code)
    print_results("Verifier Catch Rate: Code Checks Only (Deterministic)", res_code)

    if a.with_critic:
        from src.llm import get_llm
        v_full = Verifier(llm=get_llm())
        res_full = run_injection_suite(v_full)
        print_results("Verifier Catch Rate: With LLM Critic", res_full)


if __name__ == "__main__":
    main()
