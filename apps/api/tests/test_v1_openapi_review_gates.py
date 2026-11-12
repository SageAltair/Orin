"""Regression tests for review-only OpenAPI contract gates (#179)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from freeze_v1_openapi import canonical_contract
from report_v1_openapi_security import inventory
from validate_v1_openapi_candidate import validate


def candidate():
    return {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/private": {
                "get": {
                    "operationId": "get_private",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/api/v1/public": {
                "get": {"operationId": "get_public", "security": [], "responses": {"200": {"description": "ok"}}}
            },
        },
        "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}},
    }


def test_candidate_preserves_schema_and_security_details():
    doc = candidate()
    doc["components"]["schemas"] = {"Record": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}}
    doc["paths"]["/health"] = {"get": {"operationId": "health"}}
    frozen = canonical_contract(doc)
    assert "/health" not in frozen["paths"]
    assert frozen["components"]["schemas"]["Record"]["required"] == ["id"]
    assert frozen["paths"]["/api/v1/private"]["get"]["security"] == [{"BearerAuth": []}]


def test_candidate_rejects_unresolved_refs_and_unknown_security_schemes():
    doc = candidate()
    doc["paths"]["/api/v1/private"]["get"]["responses"]["200"]["content"] = {
        "application/json": {"schema": {"$ref": "#/components/schemas/Absent"}}
    }
    doc["paths"]["/api/v1/private"]["get"]["security"] = [{"MissingAuth": []}]
    errors = validate(doc)
    assert any("unresolved reference" in error for error in errors)
    assert any("unknown security scheme" in error for error in errors)


def test_candidate_rejects_duplicate_operation_ids():
    doc = candidate()
    doc["paths"]["/api/v1/public"]["get"]["operationId"] = "get_private"
    assert any("Duplicate operationId" in error for error in validate(doc))


def test_security_inventory_distinguishes_public_from_authenticated():
    records = inventory(candidate())
    by_path = {record["path"]: record for record in records}
    assert by_path["/api/v1/public"]["anonymous_allowed"] is True
    assert by_path["/api/v1/private"]["anonymous_allowed"] is False
    assert by_path["/api/v1/private"]["undefined_security_schemes"] == []
