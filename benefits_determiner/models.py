from __future__ import annotations
from datetime import date
from pydantic import BaseModel


class DataServiceError(Exception):
    pass


class DetermineRequest(BaseModel):
    member_id: str
    provider_id: str
    procedure_codes: list[str]
    date_of_service: date


class LineDetermination(BaseModel):
    procedure_code: str
    covered: bool
    requires_auth: bool
    auth_on_file: str | None
    denial_reason: str | None


class DetermineResponse(BaseModel):
    member_id: str
    plan_id: str | None
    eligible: bool
    network_status: str | None
    overall_covered: bool
    line_determinations: list[LineDetermination]
    denial_reason: str | None
