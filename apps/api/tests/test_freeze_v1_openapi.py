"""Regression tests for the v1 OpenAPI freeze projection.

These tests are deliberately independent of application startup and a database.
The authoritative runtime snapshot is a separate release gate.
"""
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "freeze_v1_openapi.py"
SPEC = importlib.util.spec_from_file_location("freeze_v1_openapi", SCRIPT)
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


def sample_document():
    return {
        "openapi": "3.1.0",
        "info": {"title": "Orin", "version": "1.0"},
        "paths": {
            "/api/v1/tasks": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Task"}
                                }
                            }
                        }
                    },
                    "security": [{"Bearer": []}],
                },
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TaskInput"}
                            }
                        },
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/health": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
        "components": {
            "schemas": {
                "Task": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                },
                "TaskInput": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string"}},
                },
            },
            "securitySchemes": {"Bearer": {"type": "http", "scheme": "bearer"}},
        },
    }


def test_projection_keeps_field_types_requiredness_and_auth():
    projected = freeze.canonical_contract(sample_document())
    assert "/health" not in projected["paths"]
    assert projected["components"]["schemas"]["Task"]["required"] == ["id"]
    assert projected["components"]["schemas"]["TaskInput"]["properties"]["title"]["type"] == "string"
    assert projected["paths"]["/api/v1/tasks"]["get"]["security"] == [{"Bearer": []}]
    assert projected["paths"]["/api/v1/tasks"]["post"]["requestBody"]["required"] is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["components"]["schemas"]["Task"]["properties"]["id"].update(type="string"),
        lambda doc: doc["components"]["schemas"]["TaskInput"].update(required=[]),
        lambda doc: doc["paths"]["/api/v1/tasks"]["get"].update(security=[]),
        lambda doc: doc["paths"]["/api/v1/tasks"]["post"]["requestBody"].update(required=False),
        lambda doc: doc["paths"]["/api/v1/tasks"]["get"]["responses"].update({"200": {"description": "changed"}}),
    ],
)
def test_serialized_contract_detects_critical_drift(mutate):
    original = sample_document()
    changed = sample_document()
    mutate(changed)
    assert freeze.serialize(original) != freeze.serialize(changed)


def test_serialization_is_deterministic_across_key_order():
    original = sample_document()
    reordered = dict(reversed(list(original.items())))
    assert freeze.serialize(original) == freeze.serialize(reordered)


def test_rejects_missing_versioned_paths():
    doc = sample_document()
    doc["paths"] = {"/health": doc["paths"]["/health"]}
    with pytest.raises(ValueError, match="No versioned API paths"):
        freeze.canonical_contract(doc)
