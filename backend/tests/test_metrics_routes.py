from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_root_metrics_route_is_not_exposed():
    response = client.get("/metrics")

    assert response.status_code == 404


def test_api_metrics_route_remains_available():
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert "fdsm_app_info" in response.text
