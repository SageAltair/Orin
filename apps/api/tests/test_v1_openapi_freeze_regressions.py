"""Regression coverage for the v1 OpenAPI freeze projection.

These tests deliberately do not import the application or write an approved baseline.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "freeze_v1_openapi.py"
spec = importlib.util.spec_from_file_location("freeze_v1_openapi_contract_under_test", SCRIPT)
assert spec and spec.loader
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


def document():
    return {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/tasks": {
                "get": {
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "OK"}},
                },
                "parameters": [{"name": "x-client", "in": "header", "schema": {"type": "string"}}],
                "summary": "Excluded path metadata",
            },
            "/health": {"get": {"responses": {"200": {"description": "OK"}}}},
        },
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {"Task": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}},
        },
        "security": [],
    }


def test_projection_excludes_unversioned_routes_and_preserves_contract_fields():
    source = document()
    original = copy.deepcopy(source)
    result = freeze.canonical_contract(source)
    assert list(result["paths"]) == ["/api/v1/tasks"]
    assert "summary" not in result["paths"]["/api/v1/tasks"]
    assert result["paths"]["/api/v1/tasks"]["parameters"] == source["paths"]["/api/v1/tasks"]["parameters"]
    assert result["components"]["schemas"] == source["components"]["schemas"]
    assert source == original


@pytest.mark.parametrize("change", ["auth", "required", "response", "parameter"])
def test_serialized_contract_detects_critical_drift(change):
    source = document()
    changed = copy.deepcopy(source)
    operation = changed["paths"]["/api/v1/tasks"]["get"]
    if change == "auth":
        operation["security"] = []
    elif change == "required":
        changed["components"]["schemas"]["Task"]["required"] = []
    elif change == "response":
        operation["responses"]["200"]["description"] = "Different"
    else:
        changed["paths"]["/api/v1/tasks"]["parameters"][0]["schema"]["type"] = "integer"
    assert freeze.serialize(source) != freeze.serialize(changed)


def test_serialization_is_stable_across_mapping_insertion_order():
    source = document()
    reordered = copy.deepcopy(source)
    reordered["paths"] = dict(reversed(list(reordered["paths"].items())))
    assert freeze.serialize(source) == freeze.serialize(reordered)


def test_empty_versioned_surface_is_rejected():
    source = document()
    source["paths"] = {"/health": source["paths"]["/health"]}
    with pytest.raises(ValueError, match="No versioned API paths"):
        freeze.canonical_contract(source)
