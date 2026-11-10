"""Build the ExtractedClaim a perfect extractor would return, straight from claim.json.

Used to develop and test the stages after extraction without spending LLM calls, and later to separate
extraction errors from reasoning errors (oracle extraction vs real extraction).
"""
from __future__ import annotations

from src.extraction.schemas import ExtractedClaim


def oracle_extraction(claim: dict) -> ExtractedClaim:
    s, c = claim["schedule"], claim["condition"]
    history = None
    onset = None
    if c["is_ped"]:
        history = f"Known case of {c['name']}"
    return ExtractedClaim.model_validate({
        "patient_name": claim["patient"]["name"], "age": claim["patient"]["age"], "sex": claim["patient"]["sex"],
        "diagnosis": c["name"], "cause": "accident" if c["kind"] == "accident" else "illness",
        "known_history": history, "history_onset_date": onset,
        "admission_date": claim["admission_date"], "discharge_date": claim["discharge_date"],
        "length_of_stay_days": claim["room_days"], "room_category_claimed": claim["room_claimed"],
        "claimed_total": claim["stated_total"], "bill_total": claim["stated_total"],
        "items": claim["items"], "sum_insured": s["sum_insured"], "policy_start": s["policy_start"],
        "ped_waiting_months": s["ped_months"], "specified_waiting_months": s["spec_months"],
        "room_limit_per_day": s["room_limit_per_day"], "copay_pct": s["copay_pct"],
        "continuity_credit_months": s["prior_coverage_months"], "room_type_modification": s["room_type_modification"],
        "eligible_room": s["eligible_room"]})


def oracle_findings(claim: dict, rules):
    """The policy findings a perfect reader would report, built from the rule set. For engine tests only."""
    from src.adjudication.findings import Findings
    s, c = claim["schedule"], claim["condition"]
    pct = None
    if s["room_type_modification"]:
        for eligible, claimed, p in rules.room_type_copay:
            if s["eligible_room"] == eligible and claim["room_claimed"] == claimed:
                pct = p
    return Findings(initial_waiting_days=30, initial_wait_clause=rules.wait30_clause, is_specified=c["specified"],
                    spec_clause=rules.spec_clause, is_pre_existing=c["is_ped"], ped_clause=rules.ped_clause,
                    ped_def_clause=rules.ped_def_clause, room_cap_clause=rules.room_cap_clause, room_modification_copay_pct=pct,
                    room_mod_clause=rules.room_mod_clause, copay_clause=rules.copay_clause, non_payable_clause=rules.nonpayable_clause,
                    sum_insured_clause=rules.sum_insured_clause, coverage_clause=rules.coverage_clause)