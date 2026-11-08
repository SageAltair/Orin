"""Generate or verify the frozen v1 OpenAPI contract.

Run from apps/api with its test dependencies installed:
    python scripts/freeze_v1_openapi.py --write
    python scripts/freeze_v1_openapi.py --check
Never regenerate the baseline as part of CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / "contracts" / "v1-openapi.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def canonical_contract(document: dict) -> dict:
    """Preserve all field-level schemas, types, requiredness and auth declarations."""
    paths = {
        path: {
            key: value
            for key, value in operations.items()
            if key in HTTP_METHODS or key == "parameters"
        }
        for path, operations in document["paths"].items()
        if path.startswith("/api/v1/")
    }
    if not paths:
        raise ValueError("No versioned API paths found")
    return {
        "openapi": document["openapi"],
        "paths": paths,
        "components": {
            key: value
            for key, value in document.get("components", {}).items()
            if key in {"schemas", "securitySchemes", "parameters", "responses", "requestBodies"}
        },
        "security": document.get("security", []),
    }


def serialize(document: dict) -> str:
    return json.dumps(canonical_contract(document), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Explicitly refresh frozen baseline")
    mode.add_argument("--check", action="store_true", help="Fail on any contract drift")
    args = parser.parse_args()
    from orin_api.main import app

    actual = serialize(app.openapi())
    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(actual, encoding="utf-8")
        print(f"Wrote {BASELINE}")
        return 0
    if not BASELINE.is_file():
        print(f"Missing baseline: {BASELINE}. Generate and review with --write.")
        return 1
    if BASELINE.read_text(encoding="utf-8") != actual:
        print("v1 OpenAPI drift detected. Review compatibility and approve changes before updating baseline.")
        return 1
    print("v1 OpenAPI contract matches frozen baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
