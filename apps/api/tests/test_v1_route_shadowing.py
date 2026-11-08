"""#179: detect shadowed v1 routes before OpenAPI hides them.

FastAPI's OpenAPI output is not sufficient to detect two registered handlers
with the same method and path. Starlette dispatches the first match while
OpenAPI may document the later handler, silently breaking client contracts.
"""
from collections import defaultdict

from fastapi.routing import APIRoute
from orin_api.main import app


def test_v1_has_no_shadowed_method_path_handlers() -> None:
    handlers: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/"):
            continue
        for method in route.methods or ():
            handlers[(method.upper(), route.path)].append(
                f"{route.endpoint.__module__}.{route.endpoint.__qualname__}"
            )

    assert handlers, "No v1 API handlers were inspected"
    collisions = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in handlers.items()
        if len(endpoints) > 1
    }
    assert not collisions, f"Shadowed v1 route handlers: {collisions}"
