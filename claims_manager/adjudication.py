from __future__ import annotations
from datetime import date
from decimal import Decimal
from .models import ClaimRequest, ClaimLine

_ZERO = Decimal("0")


def validate_claim(claim: ClaimRequest, seen_ids: set[str]) -> list[str]:
    errors: list[str] = []

    if not claim.claim_id:
        errors.append("claim_id: must be a non-empty string")
    elif claim.claim_id in seen_ids:
        errors.append(f"claim_id: duplicate within batch")

    if not claim.member_id:
        errors.append("member_id: must be a non-empty string")

    if not claim.provider_id:
        errors.append("provider_id: must be a non-empty string")

    if claim.date_of_service:
        try:
            date.fromisoformat(claim.date_of_service)
        except ValueError:
            errors.append("date_of_service: must be a valid YYYY-MM-DD date")
    else:
        errors.append("date_of_service: must be a valid YYYY-MM-DD date")

    if not claim.claim_lines:
        errors.append("claim_lines: at least one entry required")
    else:
        seen_line_numbers: set[int] = set()
        for line in claim.claim_lines:
            if line.line_number <= 0:
                errors.append(f"claim_lines[{line.line_number}].line_number: must be a positive integer")
            elif line.line_number in seen_line_numbers:
                errors.append(f"claim_lines: duplicate line_number {line.line_number}")
            else:
                seen_line_numbers.add(line.line_number)

            if not line.procedure_code:
                errors.append(f"claim_lines[{line.line_number}].procedure_code: must be a non-empty string")

            if line.units <= 0:
                errors.append(f"claim_lines[{line.line_number}].units: must be a positive integer")

            if line.billed_amount <= _ZERO:
                errors.append(f"claim_lines[{line.line_number}].billed_amount: must be a positive number")

    return errors


def build_denied_line(claim_line: ClaimLine, denial_reason: str) -> dict:
    return {
        "line_number": claim_line.line_number,
        "procedure_code": claim_line.procedure_code,
        "billed_amount": claim_line.billed_amount * claim_line.units,
        "allowed_amount": _ZERO,
        "contractual_adjustment": _ZERO,
        "deductible_applied": _ZERO,
        "copay_applied": _ZERO,
        "coinsurance_applied": _ZERO,
        "member_liability": _ZERO,
        "payer_liability": _ZERO,
        "adjustment_reason_code": None,
        "denial_reason": denial_reason,
        "line_status": "DENIED",
    }


def compute_claim_totals(line_details: list[dict]) -> dict:
    return {
        "billed_amount": sum(Decimal(str(ld["billed_amount"])) for ld in line_details),
        "allowed_amount": sum(Decimal(str(ld["allowed_amount"])) for ld in line_details),
        "member_liability": sum(Decimal(str(ld["member_liability"])) for ld in line_details),
        "payer_liability": sum(Decimal(str(ld["payer_liability"])) for ld in line_details),
    }


def determine_claim_status(line_details: list[dict]) -> str:
    statuses = {ld["line_status"] for ld in line_details}
    if statuses == {"PAID"}:
        return "PAID"
    if statuses == {"DENIED"}:
        return "DENIED"
    return "PARTIALLY_PAID"
