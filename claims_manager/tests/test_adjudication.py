from decimal import Decimal
import pytest
from claims_manager.models import ClaimLine, ClaimRequest
from claims_manager.adjudication import (
    validate_claim,
    build_denied_line,
    compute_claim_totals,
    determine_claim_status,
)

ZERO = Decimal("0")


def _line(line_number=1, procedure_code="99213", units=1, billed=250.00):
    return ClaimLine(
        line_number=line_number,
        procedure_code=procedure_code,
        units=units,
        billed_amount=Decimal(str(billed)),
    )


def _claim(**overrides):
    defaults = dict(
        claim_id="CLM-001",
        member_id="MBR-001",
        provider_id="PRV-001",
        date_of_service="2025-09-01",
        claim_lines=[_line()],
    )
    defaults.update(overrides)
    return ClaimRequest(**defaults)


# ===========================================================================
# validate_claim
# ===========================================================================

def test_validate_claim_valid_returns_no_errors():
    assert validate_claim(_claim(), set()) == []


def test_validate_claim_empty_claim_id():
    errors = validate_claim(_claim(claim_id=""), set())
    assert any("claim_id" in e for e in errors)


def test_validate_claim_duplicate_claim_id():
    errors = validate_claim(_claim(claim_id="CLM-001"), {"CLM-001"})
    assert any("duplicate" in e for e in errors)


def test_validate_claim_empty_member_id():
    errors = validate_claim(_claim(member_id=""), set())
    assert any("member_id" in e for e in errors)


def test_validate_claim_empty_provider_id():
    errors = validate_claim(_claim(provider_id=""), set())
    assert any("provider_id" in e for e in errors)


def test_validate_claim_invalid_date_format():
    errors = validate_claim(_claim(date_of_service="09/01/2025"), set())
    assert any("date_of_service" in e for e in errors)


def test_validate_claim_empty_claim_lines():
    errors = validate_claim(_claim(claim_lines=[]), set())
    assert any("claim_lines" in e for e in errors)


def test_validate_claim_duplicate_line_number():
    lines = [_line(line_number=1), _line(line_number=1, procedure_code="42820")]
    errors = validate_claim(_claim(claim_lines=lines), set())
    assert any("duplicate line_number" in e for e in errors)


def test_validate_claim_negative_units():
    errors = validate_claim(_claim(claim_lines=[_line(units=-1)]), set())
    assert any("units" in e for e in errors)


def test_validate_claim_zero_billed_amount():
    errors = validate_claim(_claim(claim_lines=[_line(billed=0.0)]), set())
    assert any("billed_amount" in e for e in errors)


def test_validate_claim_empty_procedure_code():
    line = ClaimLine(line_number=1, procedure_code="", units=1, billed_amount=Decimal("100"))
    errors = validate_claim(_claim(claim_lines=[line]), set())
    assert any("procedure_code" in e for e in errors)


# ===========================================================================
# build_denied_line
# ===========================================================================

def test_build_denied_line_financial_fields_are_zero():
    line = _line(billed=250.00, units=1)
    result = build_denied_line(line, "NOT_COVERED")
    assert result["allowed_amount"] == ZERO
    assert result["deductible_applied"] == ZERO
    assert result["copay_applied"] == ZERO
    assert result["coinsurance_applied"] == ZERO
    assert result["member_liability"] == ZERO
    assert result["payer_liability"] == ZERO
    assert result["contractual_adjustment"] == ZERO


def test_build_denied_line_billed_is_billed_times_units():
    line = _line(billed=250.00, units=2)
    result = build_denied_line(line, "NOT_COVERED")
    assert result["billed_amount"] == Decimal("500.00")


def test_build_denied_line_status_and_reason():
    line = _line()
    result = build_denied_line(line, "AUTH_REQUIRED_NOT_ON_FILE")
    assert result["line_status"] == "DENIED"
    assert result["denial_reason"] == "AUTH_REQUIRED_NOT_ON_FILE"
    assert result["adjustment_reason_code"] is None


# ===========================================================================
# compute_claim_totals
# ===========================================================================

PAID_LINE = {
    "billed_amount": Decimal("250.00"),
    "allowed_amount": Decimal("115.00"),
    "member_liability": Decimal("30.00"),
    "payer_liability": Decimal("85.00"),
    "line_status": "PAID",
}

DENIED_LINE = {
    "billed_amount": Decimal("4200.00"),
    "allowed_amount": ZERO,
    "member_liability": ZERO,
    "payer_liability": ZERO,
    "line_status": "DENIED",
}


def test_compute_totals_single_paid_line():
    t = compute_claim_totals([PAID_LINE])
    assert t["billed_amount"] == Decimal("250.00")
    assert t["allowed_amount"] == Decimal("115.00")
    assert t["member_liability"] == Decimal("30.00")
    assert t["payer_liability"] == Decimal("85.00")


def test_compute_totals_two_lines():
    t = compute_claim_totals([PAID_LINE, DENIED_LINE])
    assert t["billed_amount"] == Decimal("4450.00")
    assert t["allowed_amount"] == Decimal("115.00")
    assert t["member_liability"] == Decimal("30.00")
    assert t["payer_liability"] == Decimal("85.00")


def test_compute_totals_invariant():
    t = compute_claim_totals([PAID_LINE, DENIED_LINE])
    assert t["member_liability"] + t["payer_liability"] == t["allowed_amount"]


# ===========================================================================
# determine_claim_status
# ===========================================================================

def test_status_all_paid():
    lines = [{"line_status": "PAID"}, {"line_status": "PAID"}]
    assert determine_claim_status(lines) == "PAID"


def test_status_all_denied():
    lines = [{"line_status": "DENIED"}, {"line_status": "DENIED"}]
    assert determine_claim_status(lines) == "DENIED"


def test_status_mixed():
    lines = [{"line_status": "PAID"}, {"line_status": "DENIED"}]
    assert determine_claim_status(lines) == "PARTIALLY_PAID"
