from datetime import date

import pytest

from benefits_determiner.determination import (
    check_eligibility,
    check_network,
    compute_overall_covered,
    evaluate_line,
)
from benefits_determiner.models import LineDetermination

DOS = date(2025, 6, 1)

PLAN = {
    "network_provider_ids": ["PRV-10001", "PRV-10002"],
    "covered_procedure_codes": [
        {"code": "99213", "requires_auth": False},
        {"code": "42820", "requires_auth": True},
        {"code": "92504", "requires_auth": False},
    ],
    "excluded_procedure_codes": [
        {"code": "31575"},
    ],
}

VALID_AUTH = {
    "auth_id": "AUTH-001",
    "procedure_code": "42820",
    "authorized_date": "2025-05-01",
    "expiration_date": "2025-09-01",
}

EXPIRED_AUTH = {
    "auth_id": "AUTH-002",
    "procedure_code": "42820",
    "authorized_date": "2025-01-01",
    "expiration_date": "2025-03-01",
}


# --- eligibility tests ---

def test_eligibility_active_enrollment():
    enrollment = {"plan_id": "PLN-1", "effective_date": "2025-01-01", "termination_date": None}
    eligible, reason = check_eligibility(enrollment, DOS)
    assert eligible is True
    assert reason is None


def test_eligibility_termination_date_null():
    enrollment = {"plan_id": "PLN-1", "effective_date": "2025-01-01", "termination_date": None}
    eligible, _ = check_eligibility(enrollment, DOS)
    assert eligible is True


def test_eligibility_terminated_before_dos():
    enrollment = {"plan_id": "PLN-1", "effective_date": "2025-01-01", "termination_date": "2025-04-30"}
    eligible, reason = check_eligibility(enrollment, DOS)
    assert eligible is False
    assert reason == "PLAN_TERMINATED"


def test_eligibility_termination_same_day_as_dos():
    enrollment = {"plan_id": "PLN-1", "effective_date": "2025-01-01", "termination_date": "2025-06-01"}
    eligible, reason = check_eligibility(enrollment, DOS)
    assert eligible is True
    assert reason is None


# --- network tests ---

def test_network_in_network():
    assert check_network(PLAN, "PRV-10001") == "IN_NETWORK"


def test_network_out_of_network():
    assert check_network(PLAN, "PRV-99999") == "OUT_OF_NETWORK"


def test_network_empty_list():
    plan = {"network_provider_ids": []}
    assert check_network(plan, "PRV-10001") == "OUT_OF_NETWORK"


# --- procedure determination tests ---

def test_procedure_excluded():
    result = evaluate_line("31575", PLAN, [], DOS)
    assert result.covered is False
    assert result.denial_reason == "NOT_COVERED"


def test_procedure_absent_from_covered():
    result = evaluate_line("99999", PLAN, [], DOS)
    assert result.covered is False
    assert result.denial_reason == "NOT_COVERED"


def test_procedure_exclusion_takes_precedence_over_coverage():
    plan = {
        "network_provider_ids": [],
        "covered_procedure_codes": [{"code": "31575", "requires_auth": False}],
        "excluded_procedure_codes": [{"code": "31575"}],
    }
    result = evaluate_line("31575", plan, [], DOS)
    assert result.covered is False
    assert result.denial_reason == "NOT_COVERED"


def test_procedure_covered_no_auth():
    result = evaluate_line("99213", PLAN, [], DOS)
    assert result.covered is True
    assert result.requires_auth is False
    assert result.auth_on_file is None
    assert result.denial_reason is None


def test_procedure_auth_required_valid_auth():
    result = evaluate_line("42820", PLAN, [VALID_AUTH], DOS)
    assert result.covered is True
    assert result.requires_auth is True
    assert result.auth_on_file == "AUTH-001"
    assert result.denial_reason is None


def test_procedure_auth_required_no_auth():
    result = evaluate_line("42820", PLAN, [], DOS)
    assert result.covered is False
    assert result.requires_auth is True
    assert result.auth_on_file is None
    assert result.denial_reason == "AUTH_REQUIRED_NOT_ON_FILE"


def test_procedure_auth_required_expired_auth():
    result = evaluate_line("42820", PLAN, [EXPIRED_AUTH], DOS)
    assert result.covered is False
    assert result.denial_reason == "AUTH_REQUIRED_NOT_ON_FILE"


def test_procedure_auth_for_different_code_not_used():
    wrong_auth = {**VALID_AUTH, "procedure_code": "92504"}
    result = evaluate_line("42820", PLAN, [wrong_auth], DOS)
    assert result.covered is False
    assert result.denial_reason == "AUTH_REQUIRED_NOT_ON_FILE"


# --- overall covered ---

def test_overall_covered_all_true():
    lines = [
        LineDetermination(procedure_code="99213", covered=True, requires_auth=False, auth_on_file=None, denial_reason=None),
        LineDetermination(procedure_code="92504", covered=True, requires_auth=False, auth_on_file=None, denial_reason=None),
    ]
    assert compute_overall_covered(lines) is True


def test_overall_covered_one_false():
    lines = [
        LineDetermination(procedure_code="99213", covered=True, requires_auth=False, auth_on_file=None, denial_reason=None),
        LineDetermination(procedure_code="42820", covered=False, requires_auth=True, auth_on_file=None, denial_reason="AUTH_REQUIRED_NOT_ON_FILE"),
    ]
    assert compute_overall_covered(lines) is False


def test_overall_covered_empty_list():
    assert compute_overall_covered([]) is False
