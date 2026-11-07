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


def _response_schema(operation: dict, code: int) -> dict:
    """Fail when a v1 JSON response loses its declared client-visible shape."""
    return operation["responses"][str(code)]["content"]["application/json"]["schema"]


def test_v1_task_create_list_update_contract() -> None:
    """Freeze the task API methods, response status and payload declarations.

    Structural coverage only: the isolated task lifecycle tests exercise
    persistence and owner isolation separately.
    """
    collection = "/api/v1/tasks"
    item = "/api/v1/tasks/{task_id}"
    create = _operation(collection, "post")
    listing = _operation(collection, "get")
    update = _operation(item, "patch")
    assert _response_schema(create, 201)
    assert _response_schema(listing, 200)
    assert _response_schema(update, 200)
    for operation in (create, update):
        body = operation["requestBody"]
        assert body.get("required") is True
        assert body["content"]["application/json"]["schema"]
    path_parameters = update["parameters"]
    assert any(
        parameter.get("name") == "task_id"
        and parameter.get("in") == "path"
        and parameter.get("required") is True
        for parameter in path_parameters
    )


def test_v1_task_and_reminder_endpoints_do_not_expose_anonymous_access() -> None:
    """Require declared authorization on release-critical private routes."""
    for path, method in (
        ("/api/v1/tasks", "get"),
        ("/api/v1/tasks", "post"),
        ("/api/v1/tasks/{task_id}", "patch"),
        ("/api/v1/notifications/preferences", "get"),
        ("/api/v1/auth/reminder-lease", "put"),
        ("/api/v1/auth/reminder-lease", "delete"),
    ):
        operation = _operation(path, method)
        requirements = operation.get("security", app.openapi().get("security", []))
        assert requirements, f"Anonymous OpenAPI operation: {method.upper()} {path}"
        assert all(requirement for requirement in requirements), (
            f"Anonymous security alternative: {method.upper()} {path}"
        )
