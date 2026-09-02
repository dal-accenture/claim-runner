import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import MEMBER, PLAN, FEE_SCHEDULE


def test_health_success(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "UP"
    assert body["members"] == 1
    assert body["plans"] == 1
    assert body["fee_schedules"] == 1
    assert body["claims"] == 1


def test_missing_reference_file_exits_nonzero(tmp_path):
    (tmp_path / "plans.json").write_text(json.dumps([PLAN]))
    (tmp_path / "fee_schedules.json").write_text(json.dumps([FEE_SCHEDULE]))
    # members.json intentionally absent
    data_service_dir = Path(__file__).parent.parent
    script = (
        f"import os; os.environ['DATA_DIR'] = r'{tmp_path}'; "
        "import sys; sys.path.insert(0, '.'); "
        "from main import _load_all_data; _load_all_data()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        cwd=str(data_service_dir),
    )
    assert result.returncode != 0


def test_missing_claims_json_starts_normally(tmp_path, monkeypatch):
    (tmp_path / "members.json").write_text(json.dumps([MEMBER]))
    (tmp_path / "plans.json").write_text(json.dumps([PLAN]))
    (tmp_path / "fee_schedules.json").write_text(json.dumps([FEE_SCHEDULE]))
    # claims.json intentionally absent
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import main as m
    with TestClient(m.app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "UP"
        assert body["claims"] == 0
