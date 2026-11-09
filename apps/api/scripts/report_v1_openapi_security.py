"""Inventory effective OpenAPI security for explicit human review.

This is a report, not proof of runtime authentication or authorization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def inventory(document: dict) -> list[dict]:
    global_security = document.get("security", [])
    defined_schemes = set(document.get("components", {}).get("securitySchemes", {}))
    records = []
    for path, path_item in sorted(document.get("paths", {}).items()):
        for method, operation in sorted(path_item.items()):
            if method not in METHODS or not isinstance(operation, dict):
                continue
            explicit = "security" in operation
            effective = operation["security"] if explicit else global_security
            referenced_schemes = sorted({scheme for alternative in effective if isinstance(alternative, dict) for scheme in alternative}) if isinstance(effective, list) else []
            records.append({
                "undefined_security_schemes": sorted(set(referenced_schemes) - defined_schemes),
                "invalid_security_declaration": not isinstance(effective, list) or any(not isinstance(item, dict) for item in effective),
                "method": method.upper(),
                "path": path,
                "operationId": operation.get("operationId"),
                "source": "operation" if explicit else "global",
                "security": effective,
                "anonymous_allowed": not effective or (isinstance(effective, list) and {} in effective),
            })
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = inventory(json.loads(args.candidate.read_text(encoding="utf-8")))
    report = {
        "warning": "OpenAPI declarations only; inspect runtime dependencies, worker credentials, and authorization before approval.",
        "operations": len(records),
        "anonymous_or_unspecified": [r for r in records if r["anonymous_allowed"]],
        "undefined_or_invalid_security": [r for r in records if r["undefined_security_schemes"] or r["invalid_security_declaration"]],
        "inherited_global_security": [r for r in records if r["source"] == "global"],
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
