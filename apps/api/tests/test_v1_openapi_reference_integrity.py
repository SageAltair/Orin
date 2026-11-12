"""#179: validate public v1 OpenAPI references and operation identity.

The generated schema is the canonical contract source. These checks prevent
ambiguous client method generation and dangling schema references.
A versioned full-schema compatibility baseline is still required separately.
"""
from urllib.parse import unquote

from orin_api.main import app


def _resolve_pointer(document: dict, pointer: str):
    assert pointer.startswith("#/"), f"External or invalid OpenAPI reference: {pointer}"
    node = document
    for encoded in pointer[2:].split("/"):
        key = unquote(encoded).replace("~1", "/").replace("~0", "~")
        assert isinstance(node, dict) and key in node, f"Dangling OpenAPI reference: {pointer}"
        node = node[key]
    return node


def test_v1_operation_ids_are_unique_for_generated_clients() -> None:
    schema = app.openapi()
    seen = {}
    methods = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
    for path, path_item in schema["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method, operation in path_item.items():
            if method not in methods:
                continue
            identifier = operation.get("operationId")
            assert isinstance(identifier, str) and identifier.strip(), (
                f"Missing operationId for {method.upper()} {path}"
            )
            assert identifier not in seen, (
                f"Duplicate operationId {identifier}: {seen.get(identifier)} and {method.upper()} {path}"
            )
            seen[identifier] = f"{method.upper()} {path}"
    assert seen, "No versioned API operations were inspected"


def test_v1_openapi_has_no_dangling_local_references() -> None:
    schema = app.openapi()
    visited = set()

    def visit(node):
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            reference = node.get("$ref")
            if reference is not None:
                assert isinstance(reference, str)
                if reference not in visited:
                    visited.add(reference)
                    visit(_resolve_pointer(schema, reference))
            for key, value in node.items():
                if key != "$ref":
                    visit(value)

    for path, path_item in schema["paths"].items():
        if path.startswith("/api/v1/"):
            visit(path_item)
    assert visited, "No schema references were inspected"
