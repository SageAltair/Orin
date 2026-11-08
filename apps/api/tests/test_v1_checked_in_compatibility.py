"""Package #179: executable checked-in v1 compatibility baseline.

The manifest intentionally freezes release-critical public operations, not every
internal endpoint. Additive API changes are allowed; removing a declared method,
status, required request, or auth boundary requires recorded approval.
"""
import json
from pathlib import Path

from orin_api.main import app


BASELINE = Path(__file__).resolve().parents[1] / "contracts" / "v1-critical-operations.json"


def test_checked_in_v1_compatibility_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["version"] == 1
    assert baseline["namespace"] == "/api/v1"
    schema = app.openapi()
    checked = 0
    for path, methods in baseline["operations"].items():
        assert path.startswith(baseline["namespace"] + "/")
        assert path in schema["paths"], f"Breaking change: removed {path}"
        for method, expected in methods.items():
            assert method in schema["paths"][path], f"Breaking change: removed {method.upper()} {path}"
            operation = schema["paths"][path][method]
            assert set(expected["statuses"]).issubset(operation["responses"]), (
                f"Breaking change: response status removed from {method.upper()} {path}"
            )
            # Successful JSON responses must retain a machine-readable schema;
            # a status-only assertion cannot protect generated API clients.
            for status in expected["statuses"]:
                response = operation["responses"][status]
                if status == "204":
                    continue  # No Content responses have no JSON payload.
                media = response.get("content", {}).get("application/json", {})
                assert isinstance(media.get("schema"), dict) and media["schema"], (
                    f"Breaking change: JSON response schema removed from "
                    f"{method.upper()} {path} ({status})"
                )
            if expected.get("request"):
                body = operation.get("requestBody")
                assert isinstance(body, dict) and body.get("required") is True and body.get("content"), (
                    f"Breaking change: request body removed from {method.upper()} {path}"
                )
                media = body["content"].get("application/json", {})
                assert isinstance(media.get("schema"), dict) and media["schema"], (
                    f"Breaking change: JSON request schema removed from {method.upper()} {path}"
                )
            # A required body is part of the wire contract. A route that still
            # advertises JSON but silently makes it optional is incompatible.
            # The baseline does not yet freeze individual field types.
            if expected.get("auth"):
                security = operation.get("security", schema.get("security", []))
                assert security and all(isinstance(item, dict) and item for item in security), (
                    f"Breaking change: auth removed from {method.upper()} {path}"
                )
            checked += 1
    assert checked >= 9, "Critical API baseline unexpectedly emptied"
