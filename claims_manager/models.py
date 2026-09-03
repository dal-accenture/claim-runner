from __future__ import annotations
from decimal import Decimal
from typing import Annotated, List, Optional
from pydantic import BaseModel, PlainSerializer

Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DataServiceError(Exception):
    pass


class BenefitsDeterminerError(Exception):
    pass


class PricerError(Exception):
    pass


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ClaimLine(BaseModel):
    line_number: int
    procedure_code: str
    diagnosis_codes: Optional[List[str]] = None
    units: int
    billed_amount: Decimal


class ClaimRequest(BaseModel):
    claim_id: str
    member_id: str
    provider_id: str
    date_of_service: str
    claim_lines: List[ClaimLine]


class BatchRequest(BaseModel):
    claims: List[ClaimRequest]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LineDetailEntry(BaseModel):
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
    denial_reason: Optional[str]
    line_status: str


class ClaimTotals(BaseModel):
    billed_amount: Money
    allowed_amount: Money
    member_liability: Money
    payer_liability: Money


class AdjudicationResult(BaseModel):
    claim_id: str
    status: str
    adjudicated_at: Optional[str]
    totals: Optional[ClaimTotals]
    denial_reasons: List[str]
    errors: List[str]
    line_detail: List[LineDetailEntry]


class BatchResponse(BaseModel):
    results: List[AdjudicationResult]
