"""Package #179: validate the complete published OpenAPI reference graph.

The selected route sentinels guard critical endpoint names; these checks catch
dangling request/response/component references and duplicate operation IDs
across the whole API. They intentionally do not claim semantic compatibility.
"""
from collections import Counter
from urllib.parse import unquote

from orin_api.main import app


def _references(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from _references(value)
    elif isinstance(node, list):
        for item in node:
            yield from _references(item)


def _resolve_local_reference(schema, reference):
    assert reference.startswith("#/"), f"External OpenAPI reference: {reference}"
    current = schema
    for token in reference[2:].split("/"):
        token = unquote(token).replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict) and token in current, (
            f"Dangling OpenAPI reference: {reference}"
        )
        current = current[token]
    return current


def test_openapi_has_no_dangling_local_references():
    schema = app.openapi()
    for reference in _references(schema):
        _resolve_local_reference(schema, reference)


def test_openapi_operation_ids_are_unique_and_responses_declared():
    schema = app.openapi()
    operations = []
    methods = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in methods:
                continue
            assert operation.get("responses"), f"No responses: {method} {path}"
            operation_id = operation.get("operationId")
            assert operation_id, f"Missing operationId: {method} {path}"
            operations.append(operation_id)
    assert operations, "OpenAPI must expose at least one operation"
    duplicates = [name for name, count in Counter(operations).items() if count > 1]
    assert not duplicates, f"Duplicate OpenAPI operation IDs: {duplicates}"
