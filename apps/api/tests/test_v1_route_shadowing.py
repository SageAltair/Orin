"""#179: reject shadowed method/path handlers across registered FastAPI routes.

Starlette dispatches the first matching route, while OpenAPI may document a
later handler. Inspect actual APIRoute registrations rather than assuming a
particular deployment prefix: the application can mount its API at root.
"""
from collections import defaultdict

from fastapi.routing import APIRoute
from orin_api.main import app


def test_no_shadowed_method_path_handlers() -> None:
    handlers: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            handlers[(method.upper(), route.path)].append(
                f"{route.endpoint.__module__}.{route.endpoint.__qualname__}"
            )

    assert handlers, "No FastAPI route handlers were inspected"
    collisions = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in handlers.items()
        if len(endpoints) > 1
    }
    assert not collisions, f"Shadowed route handlers: {collisions}"
