from __future__ import annotations
from decimal import Decimal
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, PlainSerializer

# Serialize Decimal fields as floats in JSON responses (not strings)
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class DataServiceError(Exception):
    pass


class MemberNotFoundError(Exception):
    def __init__(self, member_id: str):
        self.member_id = member_id
        super().__init__(f"Member {member_id} not found")


class PlanNotFoundError(Exception):
    def __init__(self, plan_id: str):
        self.plan_id = plan_id
        super().__init__(f"Plan {plan_id} not found")


class ClaimLine(BaseModel):
    line_number: int
    procedure_code: str
    units: int
    billed_amount: Decimal


class PriceRequest(BaseModel):
    claim_id: str
    member_id: str
    plan_id: str
    network_status: Literal["IN_NETWORK", "OUT_OF_NETWORK"]
    claim_lines: list[ClaimLine]


class LineDetail(BaseModel):
    line_number: int
    procedure_code: str
    billed_amount: Money
    allowed_amount: Money
    contractual_adjustment: Money
    deductible_applied: Money
    copay_applied: Money
    coinsurance_applied: Money
    member_liability: Money
    payer_liability: Money
    adjustment_reason_code: Optional[str]
    line_status: str


class ClaimTotals(BaseModel):
    billed_amount: Money
    allowed_amount: Money
    member_liability: Money
    payer_liability: Money


class AccumulatorSnapshot(BaseModel):
    individual_deductible_used_before: Money
    individual_deductible_used_after: Money
    individual_oop_used_before: Money
    individual_oop_used_after: Money


class PriceResponse(BaseModel):
    claim_id: str
    totals: ClaimTotals
    accumulator_snapshot: AccumulatorSnapshot
    line_detail: list[LineDetail]
