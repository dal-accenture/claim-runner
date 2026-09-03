import pytest
import respx
import httpx
from decimal import Decimal
from fastapi.testclient import TestClient

from pricer.main import app, DATA_SERVICE_URL

MEMBER_URL = f"{DATA_SERVICE_URL}/members/MBR-10001"
PLAN_URL = f"{DATA_SERVICE_URL}/plans/PLN-GOLD-001"
FS_99213_URL = f"{DATA_SERVICE_URL}/fee-schedules/99213"
FS_42820_URL = f"{DATA_SERVICE_URL}/fee-schedules/42820"

ACTIVE_MEMBER = {
    "member_id": "MBR-10001",
    "accumulators": {
        "individual_deductible": {"limit": 500.00, "used": 125.00, "met": False},
        "individual_oop_max": {"limit": 2000.00, "used": 155.00, "met": False},
    },
}

DED_MET_MEMBER = {
    "member_id": "MBR-10002",
    "accumulators": {
        "individual_deductible": {"limit": 500.00, "used": 500.00, "met": True},
        "individual_oop_max": {"limit": 2000.00, "used": 500.00, "met": False},
    },
}

OOP_MET_MEMBER = {
    "member_id": "MBR-10003",
    "accumulators": {
        "individual_deductible": {"limit": 250.00, "used": 250.00, "met": True},
        "individual_oop_max": {"limit": 2000.00, "used": 2000.00, "met": True},
    },
}

OOP_NEAR_MEMBER = {
    "member_id": "MBR-10004",
    "accumulators": {
        "individual_deductible": {"limit": 500.00, "used": 500.00, "met": True},
        "individual_oop_max": {"limit": 2000.00, "used": 1950.00, "met": False},
    },
}

GOLD_PLAN = {"plan_id": "PLN-GOLD-001"}

FS_99213 = {
    "procedure_code": "99213",
    "in_network": {
        "allowed_amount": 115.00,
        "copay": 30.00,
        "copay_applies_before_deductible": True,
        "coinsurance_pct": 0.00,
    },
    "out_of_network": {
        "allowed_amount": 84.00,
        "copay": 0.00,
        "copay_applies_before_deductible": False,
        "coinsurance_pct": 0.40,
    },
}

FS_42820 = {
    "procedure_code": "42820",
    "in_network": {
        "allowed_amount": 2800.00,
        "copay": 0.00,
        "copay_applies_before_deductible": False,
        "coinsurance_pct": 0.10,
    },
    "out_of_network": {
        "allowed_amount": 2000.00,
        "copay": 0.00,
        "copay_applies_before_deductible": False,
        "coinsurance_pct": 0.40,
    },
}

BASE_PRICE_REQUEST = {
    "claim_id": "CLM-TEST-001",
    "member_id": "MBR-10001",
    "plan_id": "PLN-GOLD-001",
    "network_status": "IN_NETWORK",
    "claim_lines": [
        {"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}
    ],
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


# AC-1: in-network GP visit, copay before deductible, coinsurance 0%
@respx.mock
def test_ac1_gp_copay_before_deductible(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 200
    body = r.json()
    ld = body["line_detail"][0]
    assert ld["allowed_amount"] == 115.00
    assert ld["copay_applied"] == 30.00
    assert ld["deductible_applied"] == 0.00
    assert ld["coinsurance_applied"] == 0.00
    assert ld["member_liability"] == 30.00
    assert ld["payer_liability"] == 85.00
    assert body["totals"]["member_liability"] == 30.00
    assert body["totals"]["payer_liability"] == 85.00


# AC-2: in-network surgical, deductible partially met, 10% coinsurance
@respx.mock
def test_ac2_surgical_deductible_and_coinsurance(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10001").mock(
        return_value=httpx.Response(200, json=ACTIVE_MEMBER)
    )
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_42820_URL).mock(return_value=httpx.Response(200, json=FS_42820))

    req = {**BASE_PRICE_REQUEST, "claim_lines": [
        {"line_number": 1, "procedure_code": "42820", "units": 1, "billed_amount": 4200.00}
    ]}
    r = client.post("/price", json=req)
    assert r.status_code == 200
    body = r.json()
    ld = body["line_detail"][0]
    assert ld["deductible_applied"] == 375.00   # 500-125
    assert ld["coinsurance_applied"] == 242.50  # (2800-375)*0.10
    assert ld["member_liability"] == 617.50
    assert ld["payer_liability"] == 2182.50
    assert ld["member_liability"] + ld["payer_liability"] == ld["allowed_amount"]


# AC-3: deductible already met — coinsurance on full allowed amount
@respx.mock
def test_ac3_deductible_already_met(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10002").mock(
        return_value=httpx.Response(200, json=DED_MET_MEMBER)
    )
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_42820_URL).mock(return_value=httpx.Response(200, json=FS_42820))

    req = {**BASE_PRICE_REQUEST, "member_id": "MBR-10002", "claim_lines": [
        {"line_number": 1, "procedure_code": "42820", "units": 1, "billed_amount": 4200.00}
    ]}
    r = client.post("/price", json=req)
    assert r.status_code == 200
    ld = r.json()["line_detail"][0]
    assert ld["deductible_applied"] == 0.00
    assert ld["coinsurance_applied"] == 280.00  # 2800 * 0.10
    assert ld["member_liability"] == 280.00
    assert ld["payer_liability"] == 2520.00


# AC-4: OOP max already met → member_liability=0
@respx.mock
def test_ac4_oop_already_met(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10003").mock(
        return_value=httpx.Response(200, json=OOP_MET_MEMBER)
    )
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    req = {**BASE_PRICE_REQUEST, "member_id": "MBR-10003"}
    r = client.post("/price", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["member_liability"] == 0.00
    assert body["totals"]["payer_liability"] == body["totals"]["allowed_amount"]


# AC-5: OOP hit mid multi-line claim — second line has member_liability=0
@respx.mock
def test_ac5_oop_hit_mid_claim(client):
    respx.get(f"{DATA_SERVICE_URL}/members/MBR-10004").mock(
        return_value=httpx.Response(200, json=OOP_NEAR_MEMBER)
    )
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_42820_URL).mock(return_value=httpx.Response(200, json=FS_42820))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    req = {**BASE_PRICE_REQUEST, "member_id": "MBR-10004", "claim_lines": [
        {"line_number": 1, "procedure_code": "42820", "units": 1, "billed_amount": 4200.00},
        {"line_number": 2, "procedure_code": "99213", "units": 1, "billed_amount": 250.00},
    ]}
    r = client.post("/price", json=req)
    assert r.status_code == 200
    lds = r.json()["line_detail"]
    # Line 1: OOP near met (1950/2000), only 50 headroom
    assert lds[0]["member_liability"] == 50.00
    # Line 2: OOP now met, member pays nothing
    assert lds[1]["member_liability"] == 0.00


# AC-6: OON uses out_of_network rate and coinsurance
@respx.mock
def test_ac6_out_of_network_rate(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    req = {**BASE_PRICE_REQUEST, "network_status": "OUT_OF_NETWORK"}
    r = client.post("/price", json=req)
    assert r.status_code == 200
    ld = r.json()["line_detail"][0]
    assert ld["allowed_amount"] == 84.00   # OON rate, not in-network 115


# AC-7: unknown procedure code → 422
@respx.mock
def test_ac7_unknown_procedure_code(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(f"{DATA_SERVICE_URL}/fee-schedules/00000").mock(
        return_value=httpx.Response(404)
    )

    req = {**BASE_PRICE_REQUEST, "claim_lines": [
        {"line_number": 1, "procedure_code": "00000", "units": 1, "billed_amount": 100.00}
    ]}
    r = client.post("/price", json=req)
    assert r.status_code == 422
    assert "00000" in r.json()["detail"]


# AC-8: accumulator_snapshot _before/_after correct
@respx.mock
def test_ac8_accumulator_snapshot(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 200
    snap = r.json()["accumulator_snapshot"]
    assert snap["individual_deductible_used_before"] == 125.00
    assert snap["individual_deductible_used_after"] == 125.00   # copay-only, no deductible
    assert snap["individual_oop_used_before"] == 155.00
    assert snap["individual_oop_used_after"] == 185.00          # +30 copay


# AC-9: totals invariant member_liability + payer_liability == allowed_amount
@respx.mock
def test_ac9_totals_invariant(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 200
    t = r.json()["totals"]
    assert abs(t["member_liability"] + t["payer_liability"] - t["allowed_amount"]) < 0.01


# AC-10: CO-45 when billed > allowed
@respx.mock
def test_ac10_co45_present_when_billed_exceeds_allowed(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, json=GOLD_PLAN))
    respx.get(FS_99213_URL).mock(return_value=httpx.Response(200, json=FS_99213))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 200
    ld = r.json()["line_detail"][0]
    assert ld["adjustment_reason_code"] == "CO-45"
    assert ld["contractual_adjustment"] == 135.00


# AC-12: Data Service unreachable → 503
@respx.mock
def test_ac12_data_service_unreachable(client):
    respx.get(MEMBER_URL).mock(side_effect=httpx.ConnectError("unreachable"))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 503
    assert r.json()["detail"] == "Data Service unavailable"


# Member not found → 404
@respx.mock
def test_member_not_found(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(404))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 404
    assert "MBR-10001" in r.json()["detail"]


# Plan not found → 404
@respx.mock
def test_plan_not_found(client):
    respx.get(MEMBER_URL).mock(return_value=httpx.Response(200, json=ACTIVE_MEMBER))
    respx.get(PLAN_URL).mock(return_value=httpx.Response(404))

    r = client.post("/price", json=BASE_PRICE_REQUEST)
    assert r.status_code == 404
    assert "PLN-GOLD-001" in r.json()["detail"]


# 422 on missing required field (FastAPI validation)
def test_422_missing_field(client):
    r = client.post("/price", json={"claim_id": "CLM-001"})
    assert r.status_code == 422
