"""Validate a generated OpenAPI candidate without approving or freezing it.

This is a structural gate, not a substitute for human contract review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(document: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        return ["Expected an OpenAPI 3.x object"]
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append("Missing paths")
    seen_ids: set[str] = set()

    def visit(value: object, location: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{location}/{index}")
        elif isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/"):
                target: object = document
                try:
                    for segment in reference[2:].split("/"):
                        segment = segment.replace("~1", "/").replace("~0", "~")
                        if not isinstance(target, dict):
                            raise KeyError(segment)
                        target = target[segment]
                except (KeyError, TypeError):
                    errors.append(f"{location}: unresolved reference {reference}")
            for key, item in value.items():
                visit(item, f"{location}/{key}")

    if isinstance(paths, dict):
        for path, operations in paths.items():
            if not path.startswith("/api/v1/"):
                errors.append(f"Unversioned path in frozen candidate: {path}")
            if not isinstance(operations, dict):
                errors.append(f"Invalid path item: {path}")
                continue
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    continue
                if not isinstance(operation, dict):
                    errors.append(f"Invalid operation: {method} {path}")
                    continue
                operation_id = operation.get("operationId")
                if not isinstance(operation_id, str) or not operation_id:
                    errors.append(f"Missing operationId: {method} {path}")
                elif operation_id in seen_ids:
                    errors.append(f"Duplicate operationId: {operation_id}")
                else:
                    seen_ids.add(operation_id)
    visit(document, "#")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    document = json.loads(args.candidate.read_text(encoding="utf-8"))
    errors = validate(document)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("OpenAPI candidate structural integrity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
