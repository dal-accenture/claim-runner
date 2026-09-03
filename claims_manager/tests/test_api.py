import pytest
import respx
import httpx
from fastapi.testclient import TestClient

from claims_manager.main import app, DATA_SERVICE_URL, BENEFITS_DETERMINER_URL, PRICER_URL

DS = DATA_SERVICE_URL
BD = BENEFITS_DETERMINER_URL
PR = PRICER_URL

MEMBER_URL = f"{DS}/members/MBR-10042"
UNKNOWN_MEMBER_URL = f"{DS}/members/MBR-UNKNOWN"
DS_CLAIMS_URL = f"{DS}/claims"
CLAIM_CHECK_URL = f"{DS}/claims/CLM-TEST-001"
BD_URL = f"{BD}/benefits/determine"
PRICE_URL = f"{PR}/price"

ACTIVE_MEMBER = {
    "member_id": "MBR-10042",
    "accumulators": {
        "individual_deductible": {"limit": 500.0, "used": 125.0, "met": False},
        "individual_oop_max": {"limit": 2000.0, "used": 155.0, "met": False},
    },
}

BD_COVERED = {
    "member_id": "MBR-10042",
    "plan_id": "PLN-GOLD-001",
    "eligible": True,
    "network_status": "IN_NETWORK",
    "overall_covered": True,
    "line_determinations": [
        {"procedure_code": "99213", "covered": True, "requires_auth": False, "auth_on_file": None, "denial_reason": None}
    ],
    "denial_reason": None,
}

BD_MIXED = {
    "member_id": "MBR-10042",
    "plan_id": "PLN-GOLD-001",
    "eligible": True,
    "network_status": "IN_NETWORK",
    "overall_covered": False,
    "line_determinations": [
        {"procedure_code": "99213", "covered": True, "requires_auth": False, "auth_on_file": None, "denial_reason": None},
        {"procedure_code": "42820", "covered": False, "requires_auth": True, "auth_on_file": None, "denial_reason": "AUTH_REQUIRED_NOT_ON_FILE"},
    ],
    "denial_reason": None,
}

BD_ALL_DENIED = {
    "member_id": "MBR-10042",
    "plan_id": "PLN-GOLD-001",
    "eligible": True,
    "network_status": "IN_NETWORK",
    "overall_covered": False,
    "line_determinations": [
        {"procedure_code": "99213", "covered": False, "requires_auth": False, "auth_on_file": None, "denial_reason": "NOT_COVERED"}
    ],
    "denial_reason": None,
}

PRICER_RESP = {
    "claim_id": "CLM-TEST-001",
    "totals": {"billed_amount": 250.0, "allowed_amount": 115.0, "member_liability": 30.0, "payer_liability": 85.0},
    "accumulator_snapshot": {
        "individual_deductible_used_before": 125.0,
        "individual_deductible_used_after": 125.0,
        "individual_oop_used_before": 155.0,
        "individual_oop_used_after": 185.0,
    },
    "line_detail": [
        {
            "line_number": 1,
            "procedure_code": "99213",
            "billed_amount": 250.0,
            "allowed_amount": 115.0,
            "contractual_adjustment": 135.0,
            "deductible_applied": 0.0,
            "copay_applied": 30.0,
            "coinsurance_applied": 0.0,
            "member_liability": 30.0,
            "payer_liability": 85.0,
            "adjustment_reason_code": "CO-45",
            "line_status": "PAID",
        }
    ],
}

BASE_CLAIM = {
    "claim_id": "CLM-TEST-001",
    "member_id": "MBR-10042",
    "provider_id": "PRV-90210",
    "date_of_service": "2025-09-01",
    "claim_lines": [
        {"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.0}
    ],
}

BASE_BATCH = {"claims": [BASE_CLAIM]}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# AC-11: health check
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


# AC-1: valid in-network claim → PAID with correct line_detail fields
@respx.mock
def test_ac1_paid_claim(client):
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json=BD_COVERED))
    respx.post(PRICE_URL).mock(return_value=httpx.Response(200, json=PRICER_RESP))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 200
    body = r.json()
    result = body["results"][0]
    assert result["status"] == "PAID"
    ld = result["line_detail"][0]
    assert ld["allowed_amount"] == 115.0
    assert ld["copay_applied"] == 30.0
    assert ld["deductible_applied"] == 0.0
    assert ld["adjustment_reason_code"] == "CO-45"
    assert ld["line_status"] == "PAID"
    assert result["totals"]["member_liability"] == 30.0
    assert result["totals"]["payer_liability"] == 85.0


# AC-2: two-claim batch → results in submission order
@respx.mock
def test_ac2_submission_order(client):
    claim_a = {**BASE_CLAIM, "claim_id": "CLM-A"}
    claim_b = {**BASE_CLAIM, "claim_id": "CLM-B", "member_id": "MBR-10043"}

    respx.get(f"{DS}/claims/CLM-A").mock(return_value=httpx.Response(404))
    respx.get(f"{DS}/claims/CLM-B").mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(f"{DS}/members/MBR-10043").mock(return_value=httpx.Response(200, json={**ACTIVE_MEMBER, "member_id": "MBR-10043"}))
    bd_a = {**BD_COVERED, "member_id": "MBR-10042"}
    bd_b = {**BD_COVERED, "member_id": "MBR-10043"}
    respx.post(BD_URL).mock(side_effect=[
        httpx.Response(200, json=bd_a),
        httpx.Response(200, json=bd_b),
    ])
    pricer_a = {**PRICER_RESP, "claim_id": "CLM-A"}
    pricer_b = {**PRICER_RESP, "claim_id": "CLM-B"}
    respx.post(PRICE_URL).mock(side_effect=[
        httpx.Response(200, json=pricer_a),
        httpx.Response(200, json=pricer_b),
    ])
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json={"claims": [claim_a, claim_b]})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["claim_id"] == "CLM-A"
    assert results[1]["claim_id"] == "CLM-B"


# AC-3: unknown member → DENIED/NOT_ELIGIBLE, Pricer not called
@respx.mock
def test_ac3_unknown_member_not_eligible(client):
    claim = {**BASE_CLAIM, "member_id": "MBR-UNKNOWN"}
    respx.get(f"{DS}/claims/CLM-TEST-001").mock(return_value=httpx.Response(404))
    respx.get(UNKNOWN_MEMBER_URL).mock(return_value=httpx.Response(404))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json={"claims": [claim]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "DENIED"
    assert "NOT_ELIGIBLE" in result["denial_reasons"]
    assert result["line_detail"] == []
    # Verify Pricer was not called (no mock for it)


# AC-4: one covered + one denied → PARTIALLY_PAID
@respx.mock
def test_ac4_partially_paid(client):
    claim = {
        **BASE_CLAIM,
        "claim_lines": [
            {"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.0},
            {"line_number": 2, "procedure_code": "42820", "units": 1, "billed_amount": 4200.0},
        ],
    }
    pricer_resp = {
        **PRICER_RESP,
        "line_detail": [PRICER_RESP["line_detail"][0]],
    }

    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json=BD_MIXED))
    respx.post(PRICE_URL).mock(return_value=httpx.Response(200, json=pricer_resp))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json={"claims": [claim]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "PARTIALLY_PAID"
    statuses = [ld["line_status"] for ld in result["line_detail"]]
    assert "PAID" in statuses
    assert "DENIED" in statuses
    denied_line = next(ld for ld in result["line_detail"] if ld["line_status"] == "DENIED")
    assert denied_line["denial_reason"] == "AUTH_REQUIRED_NOT_ON_FILE"


# AC-5: all lines denied by BD → DENIED, Pricer not called
@respx.mock
def test_ac5_all_lines_denied(client):
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json=BD_ALL_DENIED))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "DENIED"
    assert all(ld["line_status"] == "DENIED" for ld in result["line_detail"])


# AC-8: missing required field → VALIDATION_ERROR with field name in errors
@respx.mock
def test_ac8_validation_error_empty_claim_lines(client):
    claim = {**BASE_CLAIM, "claim_lines": []}
    r = client.post("/claims/batch", json={"claims": [claim]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "VALIDATION_ERROR"
    assert any("claim_lines" in e for e in result["errors"])
    assert result["totals"] is None


# AC-9: batch with VALIDATION_ERROR + valid claim → both results returned
@respx.mock
def test_ac9_mixed_batch_validation_and_valid(client):
    invalid_claim = {**BASE_CLAIM, "claim_id": "CLM-INVALID", "claim_lines": []}
    valid_claim = {**BASE_CLAIM, "claim_id": "CLM-VALID"}

    respx.get(f"{DS}/claims/CLM-VALID").mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json={**BD_COVERED, "member_id": "MBR-10042"}))
    respx.post(PRICE_URL).mock(return_value=httpx.Response(200, json={**PRICER_RESP, "claim_id": "CLM-VALID"}))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json={"claims": [invalid_claim, valid_claim]})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2
    assert results[0]["status"] == "VALIDATION_ERROR"
    assert results[1]["status"] == "PAID"


# AC-10: duplicate claim_id already in DS → CONFLICT result
@respx.mock
def test_ac10_conflict_existing_claim(client):
    stored = {"claim_id": "CLM-TEST-001", "status": "PAID"}
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(200, json=stored))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "CONFLICT"
    assert result["errors"] == ["claim_id already exists"]


# AC-12: BD unreachable → batch returns 503
@respx.mock
def test_ac12_bd_unreachable(client):
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(side_effect=httpx.ConnectError("unreachable"))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 503
    assert r.json()["detail"] == "Service unavailable"


# Pricer unreachable → batch returns 503
@respx.mock
def test_pricer_unreachable(client):
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json=BD_COVERED))
    respx.post(PRICE_URL).mock(side_effect=httpx.ConnectError("unreachable"))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 503


# Data Service unreachable on member check → batch returns 503
@respx.mock
def test_data_service_unreachable_member_check(client):
    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(side_effect=httpx.ConnectError("unreachable"))

    r = client.post("/claims/batch", json=BASE_BATCH)
    assert r.status_code == 503


# Duplicate claim_id within batch → second gets VALIDATION_ERROR
@respx.mock
def test_duplicate_within_batch(client):
    claim_a = BASE_CLAIM
    claim_b = {**BASE_CLAIM}  # same claim_id

    respx.get(CLAIM_CHECK_URL).mock(return_value=httpx.Response(404))
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.post(BD_URL).mock(return_value=httpx.Response(200, json=BD_COVERED))
    respx.post(PRICE_URL).mock(return_value=httpx.Response(200, json=PRICER_RESP))
    respx.post(DS_CLAIMS_URL).mock(return_value=httpx.Response(201))

    r = client.post("/claims/batch", json={"claims": [claim_a, claim_b]})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["status"] == "PAID"
    assert results[1]["status"] == "VALIDATION_ERROR"
    assert any("duplicate" in e for e in results[1]["errors"])


# ---------------------------------------------------------------------------
# AC-6 & AC-7: GET /claims/{claim_id} (T013)
# ---------------------------------------------------------------------------

STORED_RESULT = {
    "claim_id": "CLM-TEST-001",
    "status": "PAID",
    "adjudicated_at": "2025-09-01T14:30:01Z",
    "totals": {"billed_amount": 250.0, "allowed_amount": 115.0, "member_liability": 30.0, "payer_liability": 85.0},
    "denial_reasons": [],
    "errors": [],
    "line_detail": [
        {
            "line_number": 1, "procedure_code": "99213",
            "billed_amount": 250.0, "allowed_amount": 115.0,
            "contractual_adjustment": 135.0,
            "deductible_applied": 0.0, "copay_applied": 30.0,
            "coinsurance_applied": 0.0, "member_liability": 30.0,
            "payer_liability": 85.0, "adjustment_reason_code": "CO-45",
            "denial_reason": None, "line_status": "PAID",
        }
    ],
}


# AC-6: stored result is retrievable with same shape
@respx.mock
def test_ac6_retrieval_found(client):
    respx.get(f"{DS}/claims/CLM-TEST-001").mock(return_value=httpx.Response(200, json=STORED_RESULT))

    r = client.get("/claims/CLM-TEST-001")
    assert r.status_code == 200
    body = r.json()
    assert body["claim_id"] == "CLM-TEST-001"
    assert body["status"] == "PAID"
    assert body["line_detail"][0]["copay_applied"] == 30.0


# AC-7: unknown claim_id → 404
@respx.mock
def test_ac7_retrieval_not_found(client):
    respx.get(f"{DS}/claims/CLM-NOTEXIST").mock(return_value=httpx.Response(404))

    r = client.get("/claims/CLM-NOTEXIST")
    assert r.status_code == 404
    assert "CLM-NOTEXIST" in r.json()["detail"]
