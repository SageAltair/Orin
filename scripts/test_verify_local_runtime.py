"""Focused, Docker-free regressions for local runtime source verification."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("verify_local_runtime.py")
spec = importlib.util.spec_from_file_location("verify_local_runtime", MODULE_PATH)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

ROOT = r"C:\Dev\Builder\02-Projects\personal\orin"


def fixtures():
    config = {"services": {
        "web": {"environment": {"VITE_API_BASE_URL": "http://localhost:8100"}},
        "api": {"environment": {"AUTH_SECRET_KEY": "test-secret", "DATABASE_URL": "test-db"}},
    }}
    containers = [
        {"Name": "/orin-web-1", "Mounts": [
            {"Type": "bind", "Source": ROOT + r"\apps\web", "Destination": "/app/apps/web"},
            {"Type": "bind", "Source": ROOT + r"\packages", "Destination": "/app/packages"}],
         "Config": {"Env": ["VITE_API_BASE_URL=http://localhost:8100"], "Cmd": ["npm", "run", "dev"]}},
        {"Name": "/orin-api-1", "Mounts": [
            {"Type": "bind", "Source": ROOT + r"\apps\api\src", "Destination": "/app/src"}],
         "Config": {"Env": ["AUTH_SECRET_KEY=test-secret", "DATABASE_URL=test-db"],
                    "Cmd": ["uvicorn", "orin_api.main:app"]}},
    ]
    return config, containers


class LocalRuntimeGuardTests(unittest.TestCase):
    def test_matching_runtime_passes(self):
        config, containers = fixtures()
        self.assertEqual(guard.assess_runtime(ROOT, config, containers), [])

    def test_detects_stale_web_source(self):
        config, containers = fixtures()
        containers[0]["Mounts"][0]["Source"] = r"C:\Users\old\Orin\apps\web"
        findings = guard.assess_runtime(ROOT, config, containers)
        self.assertTrue(any("noncanonical checkout" in f for f in findings))

    def test_detects_api_source_and_migration_startup(self):
        config, containers = fixtures()
        containers[1]["Mounts"][0]["Source"] = r"C:\Users\old\Orin\apps\api\src"
        containers[1]["Config"]["Cmd"] = ["sh", "-lc", "alembic upgrade head && uvicorn app"]
        findings = guard.assess_runtime(ROOT, config, containers)
        self.assertTrue(any("noncanonical checkout" in f for f in findings))
        self.assertTrue(any("startup command runs migrations" in f for f in findings))

    def test_env_drift_does_not_leak_secret_values(self):
        config, containers = fixtures()
        containers[1]["Config"]["Env"] = ["AUTH_SECRET_KEY=private-value", "DATABASE_URL=other-db"]
        findings = guard.assess_runtime(ROOT, config, containers)
        self.assertTrue(any("AUTH_SECRET_KEY" in f for f in findings))
        self.assertNotIn("private-value", " ".join(findings))
        self.assertNotIn("test-secret", " ".join(findings))
        self.assertNotIn("other-db", " ".join(findings))

    def test_missing_environment_key_is_reported(self):
        config, containers = fixtures()
        containers[1]["Config"]["Env"] = ["DATABASE_URL=test-db"]
        self.assertTrue(any("missing AUTH_SECRET_KEY" in f
                            for f in guard.assess_runtime(ROOT, config, containers)))

    def test_custom_project_service_labels(self):
        config, containers = fixtures()
        for service, container in zip(("web", "api"), containers):
            container["Name"] = f"/isolated-{service}-1"
            container["Config"]["Labels"] = {"com.docker.compose.service": service}
        self.assertEqual(guard.assess_runtime(ROOT, config, containers), [])

    def test_windows_paths_are_case_insensitive(self):
        self.assertEqual(guard.normalized(ROOT + r"\apps\web"),
                         guard.normalized(ROOT.lower().replace("\\", "/") + "/apps/web"))


if __name__ == "__main__":
    unittest.main()
