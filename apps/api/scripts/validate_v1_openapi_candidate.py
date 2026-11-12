"""Validate a generated OpenAPI candidate without approving or freezing it.

This is a structural gate, not a substitute for human contract review.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
from pathlib import Path


def load_document(path: Path) -> dict:
    payload = path.read_bytes()
    if path.name.endswith(".json.gz.b64"):
        payload = gzip.decompress(base64.b64decode(payload, validate=True))
    return json.loads(payload.decode("utf-8"))


def resolve_json_pointer(document: object, reference: str) -> object:
    if not reference.startswith("#/"):
        raise KeyError(reference)
    target = document
    for segment in reference[2:].split("/"):
        if any(segment[i] == "~" and (i + 1 == len(segment) or segment[i + 1] not in "01") for i in range(len(segment))):
            raise KeyError("invalid JSON pointer escape")
        segment = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(target, dict):
            target = target[segment]
        elif isinstance(target, list):
            if not segment.isdigit() or (len(segment) > 1 and segment.startswith("0")):
                raise KeyError(segment)
            index = int(segment)
            if index >= len(target):
                raise KeyError(segment)
            target = target[index]
        else:
            raise KeyError(segment)
    return target


def validate(document: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        return ["Expected an OpenAPI 3.x object"]
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append("Missing paths")
    components = document.get("components", {})
    if not isinstance(components, dict):
        errors.append("Invalid components object")
        components = {}
    schemes = components.get("securitySchemes", {})
    if not isinstance(schemes, dict):
        errors.append("Invalid securitySchemes object")
        schemes = {}
    seen_ids: set[str] = set()

    def visit(value: object, location: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{location}/{index}")
        elif isinstance(value, dict):
            reference = value.get("$ref")
            if reference is not None and not isinstance(reference, str):
                errors.append(f"{location}: invalid reference type")
            elif isinstance(reference, str) and not reference.startswith("#/"):
                errors.append(f"{location}: external reference forbidden in frozen contract: {reference}")
            elif isinstance(reference, str) and reference.startswith("#/"):
                try:
                    resolve_json_pointer(document, reference)
                except (KeyError, TypeError, ValueError):
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
    def check_security(requirements: object, location: str) -> None:
        if not isinstance(requirements, list):
            errors.append(f"{location}: security must be a list")
            return
        for index, requirement in enumerate(requirements):
            if not isinstance(requirement, dict):
                errors.append(f"{location}/{index}: invalid security requirement")
                continue
            for scheme, scopes in requirement.items():
                if scheme not in schemes:
                    errors.append(f"{location}/{index}: unknown security scheme {scheme}")
                if not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes):
                    errors.append(f"{location}/{index}: invalid security scopes for {scheme}")

    if "security" in document:
        check_security(document["security"], "#/security")
    if isinstance(paths, dict):
        for path, operations in paths.items():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                if method in {"get", "post", "put", "patch", "delete", "options", "head"} and isinstance(operation, dict) and "security" in operation:
                    check_security(operation["security"], f"#/paths/{path}/{method}/security")
    visit(document, "#")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    document = load_document(args.candidate)
    errors = validate(document)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("OpenAPI candidate structural integrity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
