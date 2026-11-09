"""Tests for the review-only effective-security inventory."""
import unittest
from report_v1_openapi_security import inventory


class SecurityInventoryTests(unittest.TestCase):
    def test_inheritance_override_and_anonymous_alternative(self):
        doc = {
            "security": [{"BearerAuth": []}],
            "paths": {
                "/api/v1/items": {
                    "get": {"operationId": "list"},
                    "post": {"operationId": "create", "security": []},
                    "delete": {"operationId": "delete", "security": [{"BearerAuth": []}, {}]},
                },
                "/api/v1/worker": {
                    "post": {"operationId": "worker", "security": [{"WorkerKey": []}]}
                },
            },
        }
        records = {r["operationId"]: r for r in inventory(doc)}
        self.assertEqual(len(records), 4)
        self.assertFalse(records["list"]["anonymous_allowed"])
        self.assertEqual(records["list"]["source"], "global")
        self.assertTrue(records["create"]["anonymous_allowed"])
        self.assertTrue(records["delete"]["anonymous_allowed"])
        self.assertFalse(records["worker"]["anonymous_allowed"])
        self.assertEqual(records["worker"]["security"], [{"WorkerKey": []}])

    def test_undefined_and_malformed_security_are_reported(self):
        doc = {
            "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}},
            "paths": {
                "/api/v1/a": {"get": {"security": [{"UnknownWorkerKey": []}]}},
                "/api/v1/b": {"post": {"security": {"BearerAuth": []}}},
                "/api/v1/c": {"get": {"security": [{"BearerAuth": []}]}},
            },
        }
        records = {r["path"]: r for r in inventory(doc)}
        self.assertEqual(records["/api/v1/a"]["undefined_security_schemes"], ["UnknownWorkerKey"])
        self.assertFalse(records["/api/v1/a"]["invalid_security_declaration"])
        self.assertTrue(records["/api/v1/b"]["invalid_security_declaration"])
        self.assertEqual(records["/api/v1/c"]["undefined_security_schemes"], [])
        self.assertFalse(records["/api/v1/c"]["invalid_security_declaration"])

    def test_malformed_security_scopes_are_rejected(self):
        doc = {"components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}}, "paths": {
            "/bad/scopes": {"get": {"security": [{"BearerAuth": "read"}]}},
            "/bad/items": {"post": {"security": [{"BearerAuth": [123]}]}},
            "/valid": {"get": {"security": [{"BearerAuth": []}]}},
        }}
        records = {r["path"]: r for r in inventory(doc)}
        self.assertTrue(records["/bad/scopes"]["invalid_security_declaration"])
        self.assertTrue(records["/bad/items"]["invalid_security_declaration"])
        self.assertFalse(records["/valid"]["invalid_security_declaration"])

    def test_no_global_security_is_flagged_for_review(self):
        records = inventory({"paths": {"/api/v1/ping": {"get": {"operationId": "ping"}}}})
        self.assertTrue(records[0]["anonymous_allowed"])
        self.assertEqual(records[0]["source"], "global")


if __name__ == "__main__":
    unittest.main()
