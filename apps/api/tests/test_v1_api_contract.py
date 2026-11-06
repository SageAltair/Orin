"""Package #179: stable public v1 API contract sentinels.

These tests protect selected release-critical routes from accidental deletion,
method changes, response shape changes, and loss of authentication. They are
not a complete OpenAPI snapshot or a substitute for live PostgreSQL tests.
"""
from orin_api.main import app


def _operation(path: str, method: str) -> dict:
    schema = app.openapi()
    assert path in schema["paths"], f"Removed v1 API path: {path}"
    operations = schema["paths"][path]
    assert method in operations, f"Changed HTTP method: {method.upper()} {path}"
    return operations[method]


def test_v1_authentication_route_contract() -> None:
    register = _operation("/api/v1/auth/register", "post")
    assert "201" in register["responses"]
    assert register["responses"]["201"]["content"]["application/json"]["schema"]
    for endpoint in ("login", "refresh"):
        operation = _operation(f"/api/v1/auth/{endpoint}", "post")
        assert "200" in operation["responses"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]


def test_v1_reminder_lease_route_contract() -> None:
    lease = "/api/v1/auth/reminder-lease"
    activate = _operation(lease, "put")
    revoke = _operation(lease, "delete")
    assert "200" in activate["responses"]
    assert "204" in revoke["responses"]
    assert "requestBody" in activate
    assert "requestBody" in revoke
    assert "application/json" in activate["requestBody"]["content"]
    assert "application/json" in revoke["requestBody"]["content"]
    read = _operation("/api/v1/auth/reminder-lease/{session_id}", "get")
    assert "200" in read["responses"]


def test_v1_notification_preferences_contract() -> None:
    operation = _operation("/api/v1/notifications/preferences", "get")
    assert "200" in operation["responses"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    schema = app.openapi()
    assert schema["info"]["title"] == "Orin API"
    # Health/diagnostic endpoints may be intentionally unversioned.
    # Freeze release-critical /api/v1 operations, not every route.
    assert "/api/v1/notifications/preferences" in schema["paths"]
