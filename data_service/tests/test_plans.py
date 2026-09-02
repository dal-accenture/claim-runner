from tests.conftest import PLAN


def test_get_plan_found(client):
    r = client.get(f"/plans/{PLAN['plan_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"] == PLAN["plan_id"]
    assert body["plan_name"] == PLAN["plan_name"]
    assert "covered_procedure_codes" in body
    assert "network_provider_ids" in body


def test_get_plan_not_found(client):
    r = client.get("/plans/PLN-DOES-NOT-EXIST")
    assert r.status_code == 404
    assert r.json()["detail"] == "plan not found"
