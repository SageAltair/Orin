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
