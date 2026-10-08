from pathlib import Path

import pytest

from orin_worker.capabilities import WorkerJob, execute_job
from orin_worker.client import JobLedger, _verify_signed, _api_url_is_secure, execute_signed_job
import hashlib
import hmac
import json


def job(action: str, parameters: dict[str, object], scope: str, **changes: object) -> WorkerJob:
    values: dict[str, object] = {"job_id": "j1", "device_id": "d1", "expires_at": 500, "nonce": "once",
        "action": action, "parameters": parameters, "scopes": [scope], "approval_id": "a1", "approved": True}
    values.update(changes)
    return WorkerJob(**values)


def test_local_worker_scopes_expiration_device_and_approval() -> None:
    roots = (Path.cwd(),)
    assert execute_job(job("get_system_info", {}, "system.info.read"), device_id="d1", allowed_roots=roots, now=10)["platform"]
    with pytest.raises(PermissionError):
        execute_job(job("get_system_info", {}, "wrong.scope"), device_id="d1", allowed_roots=roots, now=10)
    with pytest.raises(PermissionError):
        execute_job(job("get_system_info", {}, "system.info.read", device_id="d2"), device_id="d1", allowed_roots=roots, now=10)
    with pytest.raises(PermissionError):
        execute_job(job("get_system_info", {}, "system.info.read", expires_at=9), device_id="d1", allowed_roots=roots, now=10)
    with pytest.raises(PermissionError):
        execute_job(job("get_system_info", {}, "system.info.read", approved=False), device_id="d1", allowed_roots=roots, now=10)


def test_filesystem_roots_and_shell_strings_are_blocked(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("safe", encoding="utf-8")
    assert execute_job(job("read_file", {"path": str(good)}, "filesystem.file.read"), device_id="d1", allowed_roots=(tmp_path,), now=10)["content"] == "safe"
    with pytest.raises(PermissionError):
        execute_job(job("read_file", {"path": str(tmp_path.parent / "secret")}, "filesystem.file.read"), device_id="d1", allowed_roots=(tmp_path,), now=10)
    with pytest.raises(PermissionError):
        execute_job(job("run_allowed_command", {"command": "format C:"}, "process.command.execute"), device_id="d1", allowed_roots=(tmp_path,), now=10)


def test_signed_jobs_tls_requirement_and_durable_replay_ledger(tmp_path: Path) -> None:
    token = "long-test-worker-token-value"
    payload = job("get_system_info", {}, "system.info.read").model_dump(mode="json")
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(token.encode(), canonical, hashlib.sha256).hexdigest()
    assert _verify_signed({"payload": payload, "signature": signature}, token).job_id == "j1"
    with pytest.raises(ValueError, match="signature"):
        _verify_signed({"payload": payload, "signature": "bad"}, token)
    assert _api_url_is_secure("https://orin.example")
    assert not _api_url_is_secure("http://orin.example")
    assert _api_url_is_secure("http://localhost:8100")
    path = tmp_path / "ledger.db"
    ledger = JobLedger(path)
    assert ledger.start_once("j1") is True
    ledger.save_outcome("j1", "completed_pending", {"platform": "test"})
    ledger.close()
    ledger = JobLedger(path)
    assert ledger.start_once("j1") is False
    assert ledger.pending_results() == [("j1", "completed_pending", {"platform": "test"})]
    ledger.mark_reported("j1")
    assert ledger.pending_results() == []
    ledger.close()


def test_signed_job_executes_through_the_worker_boundary(tmp_path: Path) -> None:
    token = "another-long-worker-test-token"
    source = tmp_path / "input.txt"
    source.write_text("approved file", encoding="utf-8")
    worker_job = job("read_file", {"path": str(source)}, "filesystem.file.read", device_id="d-live")
    payload = worker_job.model_dump(mode="json")
    signature = hmac.new(token.encode(), json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(), hashlib.sha256).hexdigest()
    assert execute_signed_job({"payload": payload, "signature": signature}, credential=token,
        device_id="d-live", allowed_roots=(tmp_path,), now=50) == {"content": "approved file"}
    with pytest.raises(PermissionError):
        execute_signed_job({"payload": payload, "signature": signature}, credential=token,
            device_id="another-device", allowed_roots=(tmp_path,), now=50)
