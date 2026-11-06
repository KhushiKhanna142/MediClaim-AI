"""Data model for synthetic claims. Money is whole rupees (int)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

REQUIRED_DOCS = ("claim_form", "hospital_bill", "discharge_summary", "id_proof")


@dataclass
class Schedule:
    """What a real policy schedule/certificate would state for this policyholder."""
    sum_insured: int
    policy_start: date
    ped_months: int                       # pre-existing disease waiting period (per variant)
    spec_months: int                      # specified disease/procedure waiting period (per variant)
    room_limit_per_day: int | None = None
    copay_pct: int = 0
    prior_coverage_months: int = 0        # continuous coverage ported from an earlier policy
    room_type_modification: bool = False  # Niva 4.1.18 option
    eligible_room: str = "standard_single"


@dataclass
class Condition:
    name: str
    kind: str                             # illness | accident | cancer
    specified: bool = False               # on the policy's specified disease/procedure list
    is_ped: bool = False                  # pre-existing for this insured person


@dataclass
class LineItem:
    category: str                         # room|icu|surgeon|ot|medicine|consumable|investigation|implant|nursing|other
    description: str
    qty: int
    rate: int
    amount: int


@dataclass
class Claim:
    claim_id: str
    category: str                         # scenario label used for golden-set composition
    policy_id: str
    patient: dict
    schedule: Schedule
    condition: Condition
    admission_date: date
    discharge_date: date
    room_days: int
    room_claimed: str
    items: list[LineItem]
    stated_total: int
    docs_present: list[str] = field(default_factory=list)


def to_jsonable(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def claim_to_dict(c: Claim) -> dict:
    return to_jsonable(asdict(c))