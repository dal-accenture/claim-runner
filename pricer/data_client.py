import httpx
from .models import DataServiceError, MemberNotFoundError, PlanNotFoundError


def get_member(client: httpx.Client, base_url: str, member_id: str) -> dict:
    try:
        response = client.get(f"{base_url}/members/{member_id}")
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
        raise DataServiceError(f"Data Service unreachable: {exc}") from exc
    if response.status_code == 404:
        raise MemberNotFoundError(member_id)
    if response.status_code != 200:
        raise DataServiceError(f"Data Service returned {response.status_code} for member {member_id}")
    return response.json()


def get_plan(client: httpx.Client, base_url: str, plan_id: str) -> dict:
    try:
        response = client.get(f"{base_url}/plans/{plan_id}")
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
        raise DataServiceError(f"Data Service unreachable: {exc}") from exc
    if response.status_code == 404:
        raise PlanNotFoundError(plan_id)
    if response.status_code != 200:
        raise DataServiceError(f"Data Service returned {response.status_code} for plan {plan_id}")
    return response.json()


def get_fee_schedule(client: httpx.Client, base_url: str, procedure_code: str) -> dict | None:
    try:
        response = client.get(f"{base_url}/fee-schedules/{procedure_code}")
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
        raise DataServiceError(f"Data Service unreachable: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise DataServiceError(f"Data Service returned {response.status_code} for fee-schedule {procedure_code}")
    return response.json()
