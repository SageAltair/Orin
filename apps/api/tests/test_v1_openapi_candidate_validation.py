"""Structural OpenAPI candidate validator regression tests."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_v1_openapi_candidate.py"
spec = importlib.util.spec_from_file_location("validate_v1_openapi_candidate", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def candidate():
    return {
        "openapi": "3.1.0",
        "paths": {"/api/v1/items": {"get": {
            "operationId": "list_items",
            "responses": {"200": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Item"}
            }}}}
        }}},
        "components": {"schemas": {"Item": {"type": "object", "properties": {"id": {"type": "string"}}}}},
    }


class CandidateValidationTests(unittest.TestCase):
    def test_valid_document(self):
        self.assertEqual(module.validate(candidate()), [])

    def test_unresolved_reference(self):
        document = candidate()
        document["components"]["schemas"].pop("Item")
        self.assertTrue(any("unresolved reference" in error for error in module.validate(document)))

    def test_escaped_json_pointer(self):
        document = candidate()
        document["components"]["schemas"]["Item/Detail"] = document["components"]["schemas"].pop("Item")
        document["paths"]["/api/v1/items"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/Item~1Detail"
        self.assertEqual(module.validate(document), [])

    def test_duplicate_operation_id(self):
        document = candidate()
        document["paths"]["/api/v1/other"] = {"post": {"operationId": "list_items"}}
        self.assertTrue(any("Duplicate operationId" in error for error in module.validate(document)))

    def test_unversioned_path(self):
        document = candidate()
        document["paths"]["/health"] = {"get": {"operationId": "health"}}
        self.assertTrue(any("Unversioned path" in error for error in module.validate(document)))

    def test_missing_operation_id(self):
        document = candidate()
        del document["paths"]["/api/v1/items"]["get"]["operationId"]
        self.assertTrue(any("Missing operationId" in error for error in module.validate(document)))


if __name__ == "__main__":
    unittest.main()
