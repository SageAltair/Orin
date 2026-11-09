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

    def test_no_global_security_is_flagged_for_review(self):
        records = inventory({"paths": {"/api/v1/ping": {"get": {"operationId": "ping"}}}})
        self.assertTrue(records[0]["anonymous_allowed"])
        self.assertEqual(records[0]["source"], "global")


if __name__ == "__main__":
    unittest.main()
