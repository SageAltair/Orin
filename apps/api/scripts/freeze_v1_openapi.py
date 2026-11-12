"""Generate or verify the frozen v1 OpenAPI contract.

Run from apps/api with its test dependencies installed:
    python scripts/freeze_v1_openapi.py --write
    python scripts/freeze_v1_openapi.py --check
Never regenerate the baseline as part of CI.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import struct
from pathlib import Path
import zlib

BASELINE = Path(__file__).resolve().parents[1] / "contracts" / "v1-openapi.json.gz.b64"
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

def encode_baseline(serialized: str) -> str:
    """Return a cross-version deterministic gzip+base64 representation."""
    raw = serialized.encode("utf-8")
    compressor = zlib.compressobj(level=9, wbits=-zlib.MAX_WBITS)
    deflated = compressor.compress(raw) + compressor.flush()
    # Fixed gzip header: zero mtime, maximum compression hint, OS=unknown.
    header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    trailer = struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)
    return base64.b64encode(header + deflated + trailer).decode("ascii") + "\n"


def decode_baseline(encoded: str) -> str:
    compressed = base64.b64decode(encoded, validate=True)
    return gzip.decompress(compressed).decode("utf-8")


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
    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(encode_baseline(actual), encoding="ascii")
        print(f"Wrote compressed baseline {BASELINE}")
        return 0
    if not BASELINE.is_file():
        print(f"Missing baseline: {BASELINE}. Generate and review with --write.")
        return 1
    try:
        expected = decode_baseline(BASELINE.read_text(encoding="ascii").strip())
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"Invalid frozen OpenAPI baseline: {exc}")
        return 1
    if expected != actual:
        print("v1 OpenAPI drift detected. Review compatibility and approve changes before updating baseline.")
        return 1
    print("v1 OpenAPI contract matches frozen baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
