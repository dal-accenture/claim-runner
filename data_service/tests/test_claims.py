import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAIM, MEMBER

NEW_CLAIM = {
    "claim_id": "CLM-20260902-TEST",
    "member_id": MEMBER["member_id"],
    "provider_id": "PRV-TEST-001",
    "date_of_service": "2026-09-02",
    "received_at": "2026-09-02T10:00:00Z",
    "adjudicated_at": "2026-09-02T10:00:01Z",
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


def test_get_claim_found(client):
    r = client.get(f"/claims/{CLAIM['claim_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["claim_id"] == CLAIM["claim_id"]
    assert body["status"] == CLAIM["status"]


def test_get_claim_not_found(client):
    r = client.get("/claims/CLM-DOES-NOT-EXIST")
    assert r.status_code == 404
    assert r.json()["detail"] == "claim not found"


def test_post_claim_success_and_retrieval(client):
    r = client.post("/claims", json=NEW_CLAIM)
    assert r.status_code == 201
    body = r.json()
    assert body["claim_id"] == NEW_CLAIM["claim_id"]

    r2 = client.get(f"/claims/{NEW_CLAIM['claim_id']}")
    assert r2.status_code == 200
    assert r2.json()["claim_id"] == NEW_CLAIM["claim_id"]


def test_post_claim_duplicate_returns_409(client):
    client.post("/claims", json=NEW_CLAIM)
    r = client.post("/claims", json=NEW_CLAIM)
    assert r.status_code == 409
    assert r.json()["detail"] == "claim already exists"


def test_post_claim_missing_claim_id_returns_422(client):
    body = {k: v for k, v in NEW_CLAIM.items() if k != "claim_id"}
    r = client.post("/claims", json=body)
    assert r.status_code == 422


def test_in_memory_only(tmp_data_dir):
    import main as m

    with TestClient(m.app) as c1:
        r = c1.post("/claims", json=NEW_CLAIM)
        assert r.status_code == 201

    # New TestClient triggers fresh lifespan startup — claim is not in seed data
    with TestClient(m.app) as c2:
        r = c2.get(f"/claims/{NEW_CLAIM['claim_id']}")
        assert r.status_code == 404


async def test_concurrent_post_claims(tmp_data_dir):
    import main as m

    # Load data into module state (lifespan runs when entering the transport context)
    transport = httpx.ASGITransport(app=m.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        claim_a = {**NEW_CLAIM, "claim_id": "CLM-CONCURRENT-001"}
        claim_b = {**NEW_CLAIM, "claim_id": "CLM-CONCURRENT-002"}

        # POST both claims concurrently
        r_a, r_b = await asyncio.gather(
            ac.post("/claims", json=claim_a),
            ac.post("/claims", json=claim_b),
        )

    assert r_a.status_code == 201
    assert r_b.status_code == 201
    assert "CLM-CONCURRENT-001" in m._claims
    assert "CLM-CONCURRENT-002" in m._claims
