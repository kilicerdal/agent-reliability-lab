from fastapi.testclient import TestClient
from lab.api import app


def test_viewer_reads_captures_without_paid_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_RESULTS_DIR", str(tmp_path))
    client = TestClient(app)
    assert client.get("/runs").json() == []
    assert client.get("/health").json()["paid_requests_from_dashboard"] is False
    assert len(client.get("/scenarios").json()) == 4
    assert client.post("/runs").status_code == 405
    assert client.post("/investigate").status_code == 404
