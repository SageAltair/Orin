"""Pure contract-freeze regression tests; no database or running API required."""
import copy
import json
import unittest

from freeze_v1_openapi import canonical_contract, serialize


class FrozenOpenAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "openapi": "3.1.0",
            "info": {"title": "Orin", "version": "1"},
            "paths": {
                "/api/v1/items": {
                    "parameters": [{"name": "workspace_id", "in": "query", "schema": {"type": "string"}}],
                    "post": {
                        "operationId": "create_item",
                        "security": [{"BearerAuth": []}],
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {
                                "schema": {"$ref": "#/components/schemas/Item"}
                            }},
                        },
                        "responses": {"201": {"description": "Created"}},
                    },
                },
                "/health": {"get": {"responses": {"200": {"description": "OK"}}}},
            },
            "components": {
                "schemas": {"Item": {"type": "object", "required": ["title"],
                                      "properties": {"title": {"type": "string"}}}},
                "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            },
            "security": [],
        }

    def test_preserves_field_level_contract_and_auth(self):
        frozen = canonical_contract(self.document)
        self.assertEqual(frozen["paths"]["/api/v1/items"]["post"],
                         self.document["paths"]["/api/v1/items"]["post"])
        self.assertEqual(frozen["paths"]["/api/v1/items"]["parameters"],
                         self.document["paths"]["/api/v1/items"]["parameters"])
        self.assertEqual(frozen["components"]["schemas"],
                         self.document["components"]["schemas"])
        self.assertEqual(frozen["components"]["securitySchemes"],
                         self.document["components"]["securitySchemes"])
        self.assertNotIn("/health", frozen["paths"])
        self.assertNotIn("info", frozen)

    def test_requiredness_security_and_response_changes_are_detectable(self):
        baseline = serialize(self.document)
        variants = [
            lambda d: d["components"]["schemas"]["Item"]["required"].clear(),
            lambda d: d["paths"]["/api/v1/items"]["post"]["security"].clear(),
            lambda d: d["paths"]["/api/v1/items"]["post"]["responses"].pop("201"),
            lambda d: d["paths"]["/api/v1/items"]["post"]["requestBody"].update(required=False),
            lambda d: d["components"]["schemas"]["Item"]["properties"]["title"].update(type="integer"),
        ]
        for change in variants:
            with self.subTest(change=change):
                altered = copy.deepcopy(self.document)
                change(altered)
                self.assertNotEqual(serialize(altered), baseline)

    def test_metadata_outside_frozen_scope_does_not_cause_drift(self):
        altered = copy.deepcopy(self.document)
        altered["info"]["title"] = "Renamed"
        altered["paths"]["/health"]["get"]["responses"]["200"]["description"] = "Healthy"
        self.assertEqual(serialize(altered), serialize(self.document))

    def test_serialization_is_deterministic_and_valid_json(self):
        actual = serialize(self.document)
        self.assertEqual(json.loads(actual), canonical_contract(self.document))
        self.assertEqual(actual, serialize(copy.deepcopy(self.document)))
        self.assertTrue(actual.endswith("\n"))

    def test_rejects_document_without_versioned_paths(self):
        self.document["paths"] = {"/health": {"get": {}}}
        with self.assertRaisesRegex(ValueError, "No versioned API paths"):
            canonical_contract(self.document)


if __name__ == "__main__":
    unittest.main()
