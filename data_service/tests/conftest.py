import json
import pytest
from fastapi.testclient import TestClient

MEMBER = {
    "member_id": "MBR-TEST-001",
    "first_name": "Jane",
    "last_name": "Smith",
    "date_of_birth": "1985-04-12",
    "gender": "F",
    "contact": {"email": "jane@test.com", "phone": "555-0001", "address": "1 Test St"},
    "enrollment": {"plan_id": "PLN-TEST-001", "effective_date": "2025-01-01", "termination_date": None},
    "accumulators": {
        "plan_year": "2025",
        "individual_deductible": {"limit": 500.0, "used": 125.0, "met": False},
        "family_deductible": None,
        "individual_oop_max": {"limit": 4000.0, "used": 155.0, "met": False},
        "family_oop_max": None,
    },
    "authorizations": [],
}

PLAN = {
    "plan_id": "PLN-TEST-001",
    "plan_name": "Test PPO",
    "plan_year": "2025",
    "plan_type": "PPO",
    "effective_date": "2025-01-01",
    "termination_date": "2025-12-31",
    "network_provider_ids": ["PRV-TEST-001"],
    "covered_procedure_codes": [
        {"code": "99213", "description": "Office visit", "requires_auth": False}
    ],
    "excluded_procedure_codes": [],
}

FEE_SCHEDULE = {
    "procedure_code": "99213",
    "description": "Office visit, established patient",
    "service_category": "GP",
    "in_network": {
        "allowed_amount": 115.0,
        "copay": 30.0,
        "copay_applies_before_deductible": True,
        "coinsurance_pct": 0.0,
    },
    "out_of_network": {
        "allowed_amount": 84.0,
        "copay": 0.0,
        "copay_applies_before_deductible": False,
        "coinsurance_pct": 0.4,
    },
}

CLAIM = {
    "claim_id": "CLM-SEED-001",
    "member_id": "MBR-TEST-001",
    "provider_id": "PRV-TEST-001",
    "date_of_service": "2025-09-01",
    "received_at": "2025-09-01T14:30:00Z",
    "adjudicated_at": "2025-09-01T14:30:01Z",
    "status": "PAID",
    "totals": {
        "billed_amount": 250.0,
        "allowed_amount": 115.0,
        "member_liability": 30.0,
        "payer_liability": 85.0,
    },
    "denial_reasons": [],
    "line_detail": [
        {
            "line_number": 1,
            "procedure_code": "99213",
            "billed_amount": 250.0,
            "allowed_amount": 115.0,
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


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    (tmp_path / "members.json").write_text(json.dumps([MEMBER]))
    (tmp_path / "plans.json").write_text(json.dumps([PLAN]))
    (tmp_path / "fee_schedules.json").write_text(json.dumps([FEE_SCHEDULE]))
    (tmp_path / "claims.json").write_text(json.dumps([CLAIM]))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(tmp_data_dir):
    import main as m
    with TestClient(m.app) as c:
        yield c
