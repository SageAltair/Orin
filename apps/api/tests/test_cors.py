from fastapi.testclient import TestClient

from orin_api.main import app


def test_workspace_header_is_allowed_by_cors_preflight() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:5273",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-orin-workspace-id,authorization",
            },
        )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-orin-workspace-id" in allowed
    assert response.headers["access-control-allow-origin"] == "http://localhost:5273"
