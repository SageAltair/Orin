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

    def test_array_index_reference_resolves(self):
        self.doc["components"]["schemas"]["Item"] = {
            "oneOf": [{"type": "string"}, {"type": "integer"}]
        }
        self.doc["paths"]["/api/v1/items"]["get"]["responses"]["200"]["content"] = {
            "application/json": {"schema": {"$ref": "#/components/schemas/Item/oneOf/0"}}
        }
        self.assertEqual(validate(self.doc), [])

    def test_array_out_of_range_and_leading_zero_indices_rejected(self):
        self.doc["components"]["schemas"]["Item"] = {"oneOf": [{"type": "string"}]}
        for index in ("1", "00"):
            with self.subTest(index=index):
                self.doc["paths"]["/api/v1/items"]["get"]["responses"]["200"]["content"] = {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/Item/oneOf/{index}"}}
                }
                self.assertTrue(any("unresolved reference" in error for error in validate(self.doc)))

    def test_malformed_json_pointer_escape_rejected(self):
        self.doc["components"]["schemas"]["Item"] = {"$ref": "#/components/schemas/Bad~2Name"}
        self.assertTrue(any("unresolved reference" in error for error in validate(self.doc)))

    def test_unknown_operation_security_scheme_rejected(self):
        self.doc["paths"]["/api/v1/items"]["get"]["security"] = [{"MissingBearer": []}]
        self.assertTrue(any("unknown security scheme" in error for error in validate(self.doc)))

    def test_declared_security_scheme_accepted(self):
        self.doc["components"]["securitySchemes"] = {"BearerAuth": {"type": "http", "scheme": "bearer"}}
        self.doc["paths"]["/api/v1/items"]["get"]["security"] = [{"BearerAuth": []}]
        self.assertEqual(validate(self.doc), [])

    def test_invalid_security_scope_type_rejected(self):
        self.doc["components"]["securitySchemes"] = {"BearerAuth": {"type": "http", "scheme": "bearer"}}
        self.doc["paths"]["/api/v1/items"]["get"]["security"] = [{"BearerAuth": "read"}]
        self.assertTrue(any("invalid security scopes" in error for error in validate(self.doc)))

    def test_malformed_global_security_rejected(self):
        self.doc["security"] = {"BearerAuth": []}
        self.assertTrue(any("security must be a list" in error for error in validate(self.doc)))


if __name__ == "__main__":
    unittest.main()
