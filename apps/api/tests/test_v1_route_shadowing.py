"""#179: detect duplicate HTTP method/path handlers in the registered router.

Use route attributes instead of APIRoute class identity, which may vary
across FastAPI/Starlette versions and route wrappers.
"""
from collections import defaultdict

from orin_api.main import app


def test_no_shadowed_method_path_handlers() -> None:
    handlers: dict[tuple[str, str], list[str]] = defaultdict(list)

    def inspect(routes, prefix: str = "") -> None:
        for route in routes:
            path = prefix + getattr(route, "path", "")
            nested = getattr(route, "routes", None)
            if nested is not None:
                inspect(nested, path.rstrip("/"))
                continue
            methods = getattr(route, "methods", None)
            endpoint = getattr(route, "endpoint", None)
            if methods and endpoint is not None:
                for method in methods:
                    handlers[(method.upper(), path)].append(
                        f"{endpoint.__module__}.{endpoint.__qualname__}"
                    )

    inspect(app.routes)
    assert handlers, "No HTTP route handlers were inspected"
    collisions = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in handlers.items()
        if len(endpoints) > 1
    }
    assert not collisions, f"Shadowed route handlers: {collisions}"
