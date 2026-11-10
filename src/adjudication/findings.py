"""What the policy-reading step reports for one claim. Judgements and citations only; no money, no dates arithmetic."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator

CLAUSE_FIELDS = ("initial_wait_clause", "spec_clause", "ped_clause", "ped_def_clause", "room_cap_clause", "room_mod_clause",
                 "copay_clause", "non_payable_clause", "sum_insured_clause", "coverage_clause")


class Findings(BaseModel):
    initial_waiting_days: Optional[int] = None        # length of the initial waiting period in this policy, if it has one
    initial_wait_clause: Optional[str] = None
    is_specified: bool = False                         # diagnosis/procedure is on this policy's specified-disease list
    spec_clause: Optional[str] = None
    is_pre_existing: bool = False                      # per this policy's PED definition and the claimant's history
    ped_clause: Optional[str] = None                   # waiting-period clause for PED
    ped_def_clause: Optional[str] = None               # definition of pre-existing disease
    room_cap_clause: Optional[str] = None
    room_modification_copay_pct: Optional[int] = None  # co-pay for (eligible room, claimed room) under a room-type-modification clause
    room_mod_clause: Optional[str] = None
    copay_clause: Optional[str] = None
    non_payable_clause: Optional[str] = None
    sum_insured_clause: Optional[str] = None
    coverage_clause: Optional[str] = None
    reasoning: str = ""

    @field_validator("initial_waiting_days", "room_modification_copay_pct", mode="before")
    @classmethod
    def _int(cls, v):
        if v in (None, "", "null"):
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", str(v))
        return int(float(m.group(0))) if m else None

    @field_validator("is_specified", "is_pre_existing", mode="before")
    @classmethod
    def _bool(cls, v):
        """A model that cannot find evidence often answers null or 'no'. Treat anything but a clear yes as False."""
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "y")
        return bool(v) if v is not None else False