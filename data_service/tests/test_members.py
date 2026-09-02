from tests.conftest import MEMBER


def test_get_member_found(client):
    r = client.get(f"/members/{MEMBER['member_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["member_id"] == MEMBER["member_id"]
    assert body["first_name"] == MEMBER["first_name"]
    assert body["enrollment"] == MEMBER["enrollment"]
    assert "accumulators" in body
    assert "authorizations" in body


def test_get_member_not_found(client):
    r = client.get("/members/MBR-DOES-NOT-EXIST")
    assert r.status_code == 404
    assert r.json()["detail"] == "member not found"
