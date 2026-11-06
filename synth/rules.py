"""Per-policy rule sets used by the reference adjudicator.

clause ids are chunk clause_ids from data/processed/chunks (checked by synth/validate_ground_truth.py).
None means "not yet mapped": the ground truth then carries no citation for that rule and the validator lists it.
Only rules that are stated in the policy wording are encoded; anything that lives in the schedule is a claim input.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PROPORTIONATE = frozenset({"surgeon", "ot", "investigation", "nursing", "other"})


@dataclass(frozen=True)
class RuleSet:
    policy_id: str
    insurer: str
    wait30_clause: str | None
    ped_clause: str | None
    spec_clause: str | None
    ped_def_clause: str | None
    room_cap_clause: str | None = None
    room_mod_clause: str | None = None
    copay_clause: str | None = None
    nonpayable_clause: str | None = None
    coverage_clause: str | None = None
    sum_insured_clause: str | None = None
    # (eligible_room, claimed_room) -> additional co-payment %
    room_type_copay: tuple = ()
    proportionate_categories: frozenset = DEFAULT_PROPORTIONATE
    assumptions: tuple = ()


COMMON_ASSUMPTIONS = (
    "Proportionate deduction after a room-rent cap applies to surgeon, ot, investigation, nursing and other charges; "
    "medicine and implants are not reduced (reference simplification, check against each wording).",
    "Items of category 'consumable' are non-payable (reference simplification of the insurer's non-medical expenses list).",
    "Claims within 1 month of a waiting-period boundary are deliberately not generated.",
)

RULESETS = {
    "niva_aspire": RuleSet(
        policy_id="niva_aspire", insurer="Niva Bupa",
        wait30_clause="5.1.3", ped_clause="5.1.1", spec_clause="5.1.2", ped_def_clause="2.1.35",
        room_mod_clause="4.1.18", coverage_clause="4.1.2",
        room_type_copay=(("shared", "standard_single", 10), ("shared", "deluxe", 25), ("standard_single", "deluxe", 15)),
        assumptions=COMMON_ASSUMPTIONS + ("Room type modification co-payment (4.1.18) applies to the whole admissible amount.",),
    ),
    "hdfc_optima_secure_current": RuleSet(
        policy_id="hdfc_optima_secure_current", insurer="HDFC ERGO",
        wait30_clause="Section C", ped_clause="Section C", spec_clause="Section C", ped_def_clause="Def.35",
        room_cap_clause="2.13", nonpayable_clause="Section C", coverage_clause="1.1",
        assumptions=COMMON_ASSUMPTIONS + ("Room rent limit comes from the schedule (modelled as 1% of sum insured per day).",),
    ),
}