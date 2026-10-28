from fastapi.testclient import TestClient
import uuid

from orin_api.main import app


def test_liveness_does_not_require_database() -> None:
    request_id = str(uuid.uuid4())
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"] == request_id


def test_private_metrics_are_prometheus_compatible() -> None:
    response = TestClient(app).get("/health/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "orin_http_requests_total" in response.text
    assert "orin_background_maintenance_failures_total" in response.text
