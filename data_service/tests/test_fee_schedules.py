from tests.conftest import FEE_SCHEDULE


def test_get_fee_schedule_found(client):
    r = client.get(f"/fee-schedules/{FEE_SCHEDULE['procedure_code']}")
    assert r.status_code == 200
    body = r.json()
    assert body["procedure_code"] == FEE_SCHEDULE["procedure_code"]
    assert "in_network" in body
    assert "out_of_network" in body
    assert body["in_network"]["allowed_amount"] == FEE_SCHEDULE["in_network"]["allowed_amount"]


def test_get_fee_schedule_not_found(client):
    r = client.get("/fee-schedules/00000")
    assert r.status_code == 404
    assert r.json()["detail"] == "procedure code not found"
