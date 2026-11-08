"""#179: detect shadowed method/path handlers in nested FastAPI/Starlette routers.

Starlette dispatches the first matching route. A mounted FastAPI app can
contain APIRoutes even when the outer application has none, so traverse mounts
and nested routers instead of inspecting only the outer app.routes.
"""
from collections import defaultdict

from fastapi.routing import APIRoute
from starlette.routing import Mount
from orin_api.main import app


def test_no_shadowed_method_path_handlers() -> None:
    handlers: dict[tuple[str, str], list[str]] = defaultdict(list)

    def inspect(routes, prefix: str = "") -> None:
        for route in routes:
            if isinstance(route, Mount):
                inspect(route.routes, prefix + route.path.rstrip("/"))
            elif isinstance(route, APIRoute):
                path = prefix + route.path
                for method in route.methods or ():
                    handlers[(method.upper(), path)].append(
                        f"{route.endpoint.__module__}.{route.endpoint.__qualname__}"
                    )
            elif hasattr(route, "routes"):
                inspect(route.routes, prefix + getattr(route, "path", "").rstrip("/"))

    inspect(app.routes)
    assert handlers, "No FastAPI route handlers were inspected"
    collisions = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in handlers.items()
        if len(endpoints) > 1
    }
    assert not collisions, f"Shadowed route handlers: {collisions}"
