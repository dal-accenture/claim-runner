from datetime import date

from .models import LineDetermination


def check_eligibility(enrollment: dict, date_of_service: date) -> tuple[bool, str | None]:
    termination_date_str = enrollment.get("termination_date")
    if termination_date_str:
        termination_date = date.fromisoformat(termination_date_str)
        if termination_date < date_of_service:
            return False, "PLAN_TERMINATED"
    return True, None


def check_network(plan: dict, provider_id: str) -> str:
    if provider_id in plan.get("network_provider_ids", []):
        return "IN_NETWORK"
    return "OUT_OF_NETWORK"


def evaluate_line(
    code: str,
    plan: dict,
    authorizations: list,
    date_of_service: date,
) -> LineDetermination:
    excluded = plan.get("excluded_procedure_codes", [])
    if any(entry["code"] == code for entry in excluded):
        return LineDetermination(
            procedure_code=code,
            covered=False,
            requires_auth=False,
            auth_on_file=None,
            denial_reason="NOT_COVERED",
        )

    covered = plan.get("covered_procedure_codes", [])
    covered_entry = next((entry for entry in covered if entry["code"] == code), None)
    if covered_entry is None:
        return LineDetermination(
            procedure_code=code,
            covered=False,
            requires_auth=False,
            auth_on_file=None,
            denial_reason="NOT_COVERED",
        )

    requires_auth = covered_entry.get("requires_auth", False)
    if not requires_auth:
        return LineDetermination(
            procedure_code=code,
            covered=True,
            requires_auth=False,
            auth_on_file=None,
            denial_reason=None,
        )

    valid_auth = next(
        (
            auth for auth in authorizations
            if auth.get("procedure_code") == code
            and date.fromisoformat(auth["authorized_date"]) <= date_of_service
            and date.fromisoformat(auth["expiration_date"]) >= date_of_service
        ),
        None,
    )
    if valid_auth:
        return LineDetermination(
            procedure_code=code,
            covered=True,
            requires_auth=True,
            auth_on_file=valid_auth["auth_id"],
            denial_reason=None,
        )

    return LineDetermination(
        procedure_code=code,
        covered=False,
        requires_auth=True,
        auth_on_file=None,
        denial_reason="AUTH_REQUIRED_NOT_ON_FILE",
    )


def compute_overall_covered(line_determinations: list[LineDetermination]) -> bool:
    return bool(line_determinations) and all(ld.covered for ld in line_determinations)
