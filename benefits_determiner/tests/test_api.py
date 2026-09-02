import pytest
import respx
import httpx
from fastapi.testclient import TestClient

from benefits_determiner.main import app, DATA_SERVICE_URL

MEMBER_URL = f"{DATA_SERVICE_URL}/members/MBR-10001"
PLAN_URL = f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001"

ACTIVE_MEMBER = {
    "member_id": "MBR-10001",
    "enrollment": {
        "plan_id": "PLN-GOLD-001",
        "effective_date": "2025-01-01",
        "termination_date": None,
    },
    "authorizations": [
        {
            "auth_id": "AUTH-001",
            "procedure_code": "42820",
            "authorized_date": "2025-05-01",
            "expiration_date": "2025-09-01",
        }
    ],
}

TERMINATED_MEMBER = {
    "member_id": "MBR-10002",
    "enrollment": {
        "plan_id": "PLN-GOLD-001",
        "effective_date": "2025-01-01",
        "termination_date": "2025-04-30",
    },
    "authorizations": [],
}

GOLD_PLAN = {
    "plan_id": "PLN-GOLD-001",
    "network_provider_ids": ["PRV-10001", "PRV-10002"],
    "covered_procedure_codes": [
        {"code": "99213", "requires_auth": False},
        {"code": "42820", "requires_auth": True},
    ],
    "excluded_procedure_codes": [
        {"code": "31575"},
    ],
}

BASE_REQUEST = {
    "member_id": "MBR-10001",
    "provider_id": "PRV-10001",
    "procedure_codes": ["99213"],
    "date_of_service": "2025-06-01",
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# AC-11: health check
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# AC-1: eligible member, covered code, no auth required
@respx.mock
def test_eligible_covered_no_auth(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json=BASE_REQUEST)
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True
    assert body["overall_covered"] is True
    assert body["network_status"] == "IN_NETWORK"
    assert body["line_determinations"][0]["covered"] is True
    assert body["line_determinations"][0]["denial_reason"] is None
    assert body["denial_reason"] is None


# AC-2: plan terminated
@respx.mock
def test_plan_terminated(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10002").mock(return_value=httpx.Response(200, json=TERMINATED_MEMBER))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "member_id": "MBR-10002"})
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is False
    assert body["denial_reason"] == "PLAN_TERMINATED"
    assert body["line_determinations"] == []


# AC-3: excluded procedure → NOT_COVERED
@respx.mock
def test_excluded_procedure(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["31575"]})
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True
    assert body["overall_covered"] is False
    assert body["line_determinations"][0]["covered"] is False
    assert body["line_determinations"][0]["denial_reason"] == "NOT_COVERED"


# AC-4: auth on file, valid → covered
@respx.mock
def test_auth_on_file_valid(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["42820"]})
    assert r.status_code == 200
    body = r.json()
    line = body["line_determinations"][0]
    assert line["covered"] is True
    assert line["auth_on_file"] == "AUTH-001"
    assert line["denial_reason"] is None


# AC-5: auth required, not on file
@respx.mock
def test_auth_required_not_on_file(client):
    member_no_auth = {**ACTIVE_MEMBER, "authorizations": []}
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=member_no_auth))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["42820"]})
    assert r.status_code == 200
    line = r.json()["line_determinations"][0]
    assert line["covered"] is False
    assert line["denial_reason"] == "AUTH_REQUIRED_NOT_ON_FILE"


# AC-6: expired auth
@respx.mock
def test_auth_expired(client):
    member_expired_auth = {
        **ACTIVE_MEMBER,
        "authorizations": [{
            "auth_id": "AUTH-EXPIRED",
            "procedure_code": "42820",
            "authorized_date": "2025-01-01",
            "expiration_date": "2025-03-01",
        }],
    }
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=member_expired_auth))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["42820"]})
    assert r.status_code == 200
    line = r.json()["line_determinations"][0]
    assert line["covered"] is False
    assert line["denial_reason"] == "AUTH_REQUIRED_NOT_ON_FILE"


# AC-7: out-of-network provider, not a denial
@respx.mock
def test_out_of_network_not_denial(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "provider_id": "PRV-99999"})
    assert r.status_code == 200
    body = r.json()
    assert body["network_status"] == "OUT_OF_NETWORK"
    assert body["eligible"] is True
    assert body["denial_reason"] is None


# AC-8: mixed lines → overall_covered false
@respx.mock
def test_mixed_lines_overall_covered_false(client):
    member_no_auth = {**ACTIVE_MEMBER, "authorizations": []}
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=member_no_auth))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json=GOLD_PLAN))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["99213", "42820"]})
    assert r.status_code == 200
    body = r.json()
    assert body["overall_covered"] is False
    lines = {ld["procedure_code"]: ld for ld in body["line_determinations"]}
    assert lines["99213"]["covered"] is True
    assert lines["42820"]["covered"] is False


# AC-9: all lines covered → overall_covered true
@respx.mock
def test_all_lines_covered(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001").mock(return_value=httpx.Response(200, json={
        **GOLD_PLAN,
        "covered_procedure_codes": [
            {"code": "99213", "requires_auth": False},
            {"code": "92504", "requires_auth": False},
        ],
    }))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "procedure_codes": ["99213", "92504"]})
    assert r.status_code == 200
    assert r.json()["overall_covered"] is True


# member not found → NOT_ELIGIBLE
@respx.mock
def test_member_not_found(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-99999").mock(return_value=httpx.Response(404))

    r = client.post("/benefits/determine", json={**BASE_REQUEST, "member_id": "MBR-99999"})
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is False
    assert body["denial_reason"] == "NOT_ELIGIBLE"
    assert body["line_determinations"] == []


# AC-10: missing required field → 422
def test_missing_field_422(client):
    r = client.post("/benefits/determine", json={
        "member_id": "MBR-10001",
        "provider_id": "PRV-10001",
        "procedure_codes": ["99213"],
        # date_of_service missing
    })
    assert r.status_code == 422


# AC-12: Data Service unreachable → 503
@respx.mock
def test_data_service_unreachable(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(side_effect=httpx.ConnectError("refused"))

    r = client.post("/benefits/determine", json=BASE_REQUEST)
    assert r.status_code == 503
    assert r.json()["detail"] == "Data Service unavailable"
