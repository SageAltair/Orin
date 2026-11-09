"""Regression checks for self-contained frozen OpenAPI candidates."""
import unittest
from validate_v1_openapi_candidate import validate


class CandidateReferenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "openapi": "3.1.0",
            "paths": {"/api/v1/items": {"get": {"operationId": "get_items", "responses": {"200": {"description": "OK"}}}}},
            "components": {"schemas": {"Item": {"type": "object"}}},
        }

    def test_local_reference_resolves(self):
        self.doc["paths"]["/api/v1/items"]["get"]["responses"]["200"]["content"] = {
            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
        }
        self.assertEqual(validate(self.doc), [])

    def test_external_reference_rejected(self):
        self.doc["components"]["schemas"]["Item"] = {"$ref": "https://example.com/schema.json"}
        self.assertTrue(any("external reference" in error for error in validate(self.doc)))

    def test_missing_reference_rejected(self):
        self.doc["components"]["schemas"]["Item"] = {"$ref": "#/components/schemas/Missing"}
        self.assertTrue(any("unresolved reference" in error for error in validate(self.doc)))

    def test_non_string_reference_rejected(self):
        self.doc["components"]["schemas"]["Item"] = {"$ref": 123}
        self.assertTrue(any("invalid reference" in error for error in validate(self.doc)))


if __name__ == "__main__":
    unittest.main()
