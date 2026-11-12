"""Generate or verify the frozen v1 OpenAPI contract.

Run from apps/api with its test dependencies installed:
    python scripts/freeze_v1_openapi.py --write
    python scripts/freeze_v1_openapi.py --check
Never regenerate the baseline as part of CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / "contracts" / "v1-openapi.sha256"
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

def contract_digest(serialized: str) -> str:
    """Fingerprint the complete canonical OpenAPI contract."""
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Explicitly refresh frozen baseline")
    mode.add_argument("--check", action="store_true", help="Fail on any contract drift")
    mode.add_argument("--candidate", type=Path, help="Export a review-only candidate without changing the frozen baseline")
    args = parser.parse_args()
    from orin_api.main import app

    actual = serialize(app.openapi())
    if args.candidate:
        target = args.candidate.resolve()
        if target == BASELINE.resolve():
            parser.error("--candidate must not overwrite the frozen baseline")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(actual, encoding="utf-8")
        print(f"Wrote review-only candidate {target}")
        return 0
    actual_digest = contract_digest(actual)
    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(actual_digest + "\n", encoding="ascii")
        print(f"Wrote v1 OpenAPI SHA-256 baseline {BASELINE}: {actual_digest}")
        return 0
    if not BASELINE.is_file():
        print(f"Missing baseline: {BASELINE}. Generate and review with --write.")
        return 1
    expected = BASELINE.read_text(encoding="ascii").strip()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        print(f"Invalid SHA-256 baseline: {BASELINE}")
        return 1
    if expected != actual_digest:
        print(f"v1 OpenAPI drift detected: expected {expected}, generated {actual_digest}. Review compatibility before updating baseline.")
        return 1
    print(f"v1 OpenAPI contract matches frozen SHA-256 baseline {actual_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
