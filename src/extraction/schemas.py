"""Structured claim record produced by the extraction stage. Everything downstream (validation, adjudication)
works from this object, never from raw text. Money is whole rupees."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Category = Literal["room", "icu", "surgeon", "ot", "medicine", "consumable", "investigation", "implant", "nursing", "other"]


def _num(v):
    if isinstance(v, str):
        v = re.sub(r"[^\d.\-]", "", v)
        if v in ("", "-", "."):
            return None
    return v


def _date(v):
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
    return v


class BillItem(BaseModel):
    description: str
    qty: int = 1
    rate: Optional[int] = None
    amount: int
    category: Category


    @field_validator("qty", "rate", "amount", mode="before")
    @classmethod
    def _ints(cls, v):
        v = _num(v)
        return int(round(float(v))) if v is not None else v


class ExtractedClaim(BaseModel):
    # claim form / ID
    patient_name: str
    age: Optional[int] = None
    sex: Optional[Literal["M", "F", "O"]] = None
    policy_number: Optional[str] = None
    hospital: Optional[str] = None
    # clinical
    diagnosis: str
    cause: Literal["illness", "accident"] = "illness"
    known_history: Optional[str] = Field(None, description="past history or known case statement from the discharge summary, verbatim; null if none")
    history_onset_date: Optional[date] = Field(None, description="date a pre-existing condition was first diagnosed, if the summary states it")
    admission_date: date
    discharge_date: date
    length_of_stay_days: Optional[int] = None
    room_category_claimed: Optional[str] = None
    # money
    claimed_total: Optional[int] = Field(None, description="total amount claimed on the claim form")
    bill_total: Optional[int] = Field(None, description="grand total printed on the hospital bill")
    items: list[BillItem] = []
    # policy schedule
    sum_insured: Optional[int] = None
    policy_start: Optional[date] = None
    ped_waiting_months: Optional[int] = None
    specified_waiting_months: Optional[int] = None
    room_limit_per_day: Optional[int] = Field(None, description="null when the schedule says no limit")
    copay_pct: int = 0
    continuity_credit_months: int = 0
    room_type_modification: bool = False
    eligible_room: Optional[str] = None

    @field_validator("age", "claimed_total", "bill_total", "sum_insured", "ped_waiting_months", "specified_waiting_months",
                     "room_limit_per_day", "copay_pct", "continuity_credit_months", "length_of_stay_days", mode="before")
    @classmethod
    def _ints(cls, v):
        v = _num(v)
        return int(round(float(v))) if v is not None else v

    @field_validator("admission_date", "discharge_date", "policy_start", "history_onset_date", mode="before")
    @classmethod
    def _dates(cls, v):
        return _date(v)

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, v):
        return {"male": "M", "female": "F"}.get(str(v).strip().lower(), str(v).strip().upper()[:1]) if v else v

    @field_validator("room_category_claimed", "eligible_room", mode="before")
    @classmethod
    def _room(cls, v):
        return re.sub(r"[\s\-]+", "_", v.strip().lower()) if isinstance(v, str) else v