from pathlib import Path

import pytest

from orin_worker import capabilities
from orin_worker.capabilities import WorkerJob, _run_bounded, execute_job
from orin_worker.client import JobLedger, _verify_signed, _api_url_is_secure, execute_signed_job
import hashlib
import hmac
import json
import subprocess
import sys


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
    with pytest.raises(PermissionError):
        execute_job(job("run_allowed_command", {"command": "git_status && whoami"}, "process.command.execute"), device_id="d1", allowed_roots=(tmp_path,), now=10)


def test_worker_protects_env_variants_and_symlink_escapes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    protected = root / ".env.example"
    protected.write_text("placeholder", encoding="utf-8")
    with pytest.raises(PermissionError):
        execute_job(job("read_file", {"path": str(protected)}, "filesystem.file.read"), device_id="d1", allowed_roots=(root,), now=10)
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not available in this environment")
    with pytest.raises(PermissionError):
        execute_job(job("read_file", {"path": str(link)}, "filesystem.file.read"), device_id="d1", allowed_roots=(root,), now=10)


def test_allowlisted_process_uses_fixed_args_bounded_timeout_and_clean_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("ORIN_WORKER_TOKEN", "must-not-reach-child")
    def fake_run(argv: tuple[str, ...], **kwargs: object) -> dict[str, object]:
        captured.update(argv=argv, **kwargs)
        return {"return_code": 0, "stdout": "clean", "stderr": ""}
    monkeypatch.setattr(capabilities, "_run_bounded", fake_run)
    output = execute_job(job("run_allowed_command", {"command": "git_status"}, "process.command.execute"), device_id="d1", allowed_roots=(tmp_path,), now=10)
    assert output["stdout"] == "clean"
    assert captured["cwd"] == str(tmp_path.resolve())
    assert "must-not-reach-child" not in captured["env"].values()


def test_command_output_and_runtime_are_bounded() -> None:
    noisy = (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 1_100_000)")
    with pytest.raises(ValueError, match="output exceeds"):
        _run_bounded(noisy, timeout=10)
    sleeper = (sys.executable, "-c", "import time; time.sleep(5)")
    with pytest.raises(TimeoutError, match="time limit"):
        _run_bounded(sleeper, timeout=0.05)
    invalid = (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'good\\xffbad')")
    assert _run_bounded(invalid, timeout=10)["stdout"] == "good�bad"


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


def test_project_test_commands_fail_closed_without_isolation(tmp_path, monkeypatch):
    monkeypatch.delenv("ORIN_WORKER_EXECUTION_IMAGE", raising=False)
    with pytest.raises(PermissionError, match="isolated"):
        execute_job(job("run_allowed_command", {"command": "python_tests"}, "process.command.execute"),
                    device_id="d1", allowed_roots=(tmp_path,), now=50)


def test_started_worker_job_recovers_as_failed_instead_of_replaying(tmp_path):
    path = tmp_path / "interrupted.sqlite3"
    ledger = JobLedger(path)
    ledger.start_once("interrupted")
    ledger.mark_started("interrupted")
    ledger.close()
    recovered = JobLedger(path)
    assert recovered.pending_results() == [("interrupted", "failed_pending", None)]
    assert not recovered.start_once("interrupted")
    recovered.close()


def test_project_sandbox_excludes_credentials_and_live_files(tmp_path, monkeypatch):
    import os
    import subprocess
    if os.name != "posix":
        pytest.skip("Linux isolation runner")
    (tmp_path / ".env").write_text("secret-token")
    (tmp_path / "code.py").write_text("print('test')")
    (tmp_path / "outside-link").symlink_to(tmp_path / ".env")
    monkeypatch.setenv("ORIN_WORKER_EXECUTION_IMAGE", "orin-test:verified")
    def run(argv, **kwargs):
        assert "--network=none" in argv and "--read-only" in argv and "--cap-drop=ALL" in argv
        mount = argv[argv.index("--mount") + 1]
        source = Path(mount.split("src=", 1)[1].split(",", 1)[0])
        assert not (source / ".env").exists()
        assert not (source / "outside-link").exists()
        assert (source / "code.py").is_file()
        assert source != tmp_path
        return {"return_code": 0, "stdout": "passed", "stderr": ""}
    monkeypatch.setattr(capabilities, "_run_bounded", run)
    result = execute_job(job("run_allowed_command", {"command": "python_tests"}, "process.command.execute"),
                         device_id="d1", allowed_roots=(tmp_path,), now=50)
    assert result["stdout"] == "passed"
