from __future__ import annotations
import httpx
from .models import DataServiceError, BenefitsDeterminerError, PricerError


def _ds_call(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    try:
        resp = client.request(method, url, **kwargs)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
        raise DataServiceError(str(exc)) from exc
    if resp.status_code >= 500:
        raise DataServiceError(f"Data Service returned {resp.status_code}")
    return resp


def get_member(client: httpx.Client, base_url: str, member_id: str) -> dict | None:
    resp = _ds_call(client, "GET", f"{base_url}/members/{member_id}")
    if resp.status_code == 404:
        return None
    return resp.json()


def get_claim(client: httpx.Client, base_url: str, claim_id: str) -> dict | None:
    resp = _ds_call(client, "GET", f"{base_url}/claims/{claim_id}")
    if resp.status_code == 404:
        return None
    return resp.json()


def post_claim(client: httpx.Client, base_url: str, result: dict) -> None:
    _ds_call(client, "POST", f"{base_url}/claims", json=result)


def determine_benefits(client: httpx.Client, base_url: str, payload: dict) -> dict:
    try:
        resp = client.post(f"{base_url}/benefits/determine", json=payload)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
        raise BenefitsDeterminerError(str(exc)) from exc
    if resp.status_code >= 500:
        raise BenefitsDeterminerError(f"Benefits Determiner returned {resp.status_code}")
    return resp.json()


def price_claim(client: httpx.Client, base_url: str, payload: dict) -> dict:
    try:
        resp = client.post(f"{base_url}/price", json=payload)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
        raise PricerError(str(exc)) from exc
    if resp.status_code >= 500:
        raise PricerError(f"Pricer returned {resp.status_code}")
    return resp.json()
