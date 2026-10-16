"""Fail-closed local worker capabilities. No shell strings or implicit filesystem roots."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from itertools import islice
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCOPES = {
    "get_system_info": "system.info.read",
    "list_directory": "filesystem.directory.read",
    "read_file": "filesystem.file.read",
    "write_file": "filesystem.file.write",
    "run_allowed_command": "process.command.execute",
    "show_notification": "device.notification.send",
    "launch_app": "device.application.launch",
}
ALLOWED_COMMANDS: dict[str, tuple[str, ...]] = {
    "git_status": ("git", "-c", "core.fsmonitor=false", "status", "--short"),
    "git_version": ("git", "--version"),
    "python_tests": (sys.executable, "-m", "pytest", "-q"),
    "npm_tests": ("npm", "test", "--", "--run"),
}

_PROTECTED_NAMES = {".ssh", ".aws", ".azure", ".config", "credentials", "secrets", "program files", "program files (x86)", "programdata", "windows", "id_rsa", "id_ed25519"}
_MAX_COMMAND_OUTPUT_BYTES = 1_000_000


def _run_bounded(argv: tuple[str, ...], *, cwd: str | None = None,
                 env: dict[str, str] | None = None, timeout: float = 120) -> dict[str, Any]:
    """Run a fixed argv while bounding combined output retained by the host."""
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, shell=False)
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def drain(name: str, stream: Any) -> None:
        nonlocal total
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            with lock:
                previous_total = total
                total += len(chunk)
                remaining = max(0, _MAX_COMMAND_OUTPUT_BYTES - previous_total)
                chunks[name].extend(chunk[:remaining])
                if total > _MAX_COMMAND_OUTPUT_BYTES:
                    overflow.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                    return

    threads = [threading.Thread(target=drain, args=(name, stream), daemon=True)
               for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for thread in threads:
        thread.start()
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise TimeoutError("Command exceeded the execution time limit") from exc
    finally:
        for thread in threads:
            thread.join(timeout=2)
    if overflow.is_set():
        raise ValueError("Command output exceeds the 1 MB limit")
    return {"return_code": return_code,
            "stdout": bytes(chunks["stdout"]).decode("utf-8", errors="replace")[:4000],
            "stderr": bytes(chunks["stderr"]).decode("utf-8", errors="replace")[:1000]}


class WorkerJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_id: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=80)
    expires_at: int
    action: str
    parameters: dict[str, Any]
    scopes: list[str]
    approval_id: str | None = None
    approved: bool = False
    nonce: str = Field(min_length=1, max_length=64)


def _path(raw: str, roots: tuple[Path, ...]) -> Path:
    candidate = Path(raw).expanduser().resolve(strict=False)
    if not roots or not any(candidate == root or root in candidate.parents for root in roots):
        raise PermissionError("Path is outside configured worker roots")
    if any(part.casefold() in _PROTECTED_NAMES or part.casefold().startswith(".env") for part in candidate.parts):
        raise PermissionError("Access to protected credential locations is blocked")
    return candidate


def _run_project_tests(command_key: str, project_root: Path) -> dict[str, Any]:
    import re
    import shutil
    import tempfile
    image = os.environ.get("ORIN_WORKER_EXECUTION_IMAGE", "")
    if not image or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9./:@_-]{0,240}", image):
        raise PermissionError("Project tests require a configured isolated execution image")
    if os.name != "posix":
        raise PermissionError("Run project commands on an enrolled Linux sandbox worker")
    # Never mount the live project: credentials, symlinks and VCS settings stay on the host.
    with tempfile.TemporaryDirectory(prefix="orin-sandbox-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        total, files = 0, 0
        ignored = _PROTECTED_NAMES | {".git", "node_modules", ".venv", "venv", "__pycache__"}
        for folder, directories, names in os.walk(project_root, followlinks=False):
            base = Path(folder)
            directories[:] = [name for name in directories if name.casefold() not in ignored
                               and not name.casefold().startswith(".env") and not (base / name).is_symlink()]
            destination = source / base.relative_to(project_root)
            destination.mkdir(parents=True, exist_ok=True)
            for name in names:
                path = base / name
                if name.casefold() in ignored or name.casefold().startswith(".env") or path.is_symlink() or not path.is_file():
                    continue
                total += path.stat().st_size; files += 1
                if total > 50_000_000 or files > 5000:
                    raise ValueError("Project snapshot exceeds the sandbox size limit")
                shutil.copyfile(path, destination / name)
        command = ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider") if command_key == "python_tests" else ("npm", "test", "--", "--run")
        container_name = f"orin-job-{uuid.uuid4().hex}"
        argv = ("docker", "run", "--name", container_name, "--rm", "--pull=never", "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=128",
                "--memory=512m", "--cpus=1", "--user", f"{os.getuid() or 10001}:{os.getgid() or 10001}",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--mount", f"type=bind,src={source},dst=/workspace,readonly", "--workdir=/workspace", image, *command)
        environment = {key: value for key, value in os.environ.items() if key.upper() == "PATH"}
        try:
            return _run_bounded(argv, env=environment)
        except (TimeoutError, ValueError):
            subprocess.run(("docker", "rm", "-f", container_name), env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                shell=False, check=False)
            raise


def execute_job(job: WorkerJob, *, device_id: str, allowed_roots: tuple[Path, ...], now: int) -> dict[str, Any]:
    if job.device_id != device_id:
        raise PermissionError("Job belongs to a different device")
    if job.expires_at <= now:
        raise PermissionError("Job has expired")
    if not job.approved or not job.approval_id:
        raise PermissionError("Job has no matching user approval")
    required = SCOPES.get(job.action)
    if not required or required not in job.scopes:
        raise PermissionError("Required worker scope is missing")
    params = job.parameters
    if job.action == "get_system_info":
        return {"platform": os.name, "python": __import__("platform").python_version()}
    if job.action == "show_notification":
        if os.name != "nt":
            raise PermissionError("Desktop notifications are currently available on Windows workers")
        title, message = params.get("title"), params.get("message")
        if not isinstance(title, str) or not isinstance(message, str) or not title or not message:
            raise ValueError("Notification content is invalid")
        script = "Add-Type -AssemblyName System.Windows.Forms;[System.Windows.Forms.MessageBox]::Show($args[1],$args[0])|Out-Null"
        _run_bounded(("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, title[:120], message[:500]), timeout=30)
        return {"delivered": True}
    if job.action == "launch_app":
        if os.name != "nt":
            raise PermissionError("Application launching is currently available on Windows workers")
        executable = {"calculator": "calc.exe", "settings": "explorer.exe"}.get(params.get("app_id"))
        if executable is None:
            raise PermissionError("Application is not on the worker allowlist")
        argv = (executable, "ms-settings:") if params.get("app_id") == "settings" else (executable,)
        subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"launched": params["app_id"]}
    if job.action == "list_directory":
        path = _path(str(params.get("path", "")), allowed_roots)
        if not path.is_dir():
            raise ValueError("Directory does not exist")
        return {"entries": [{"name": item.name, "is_directory": item.is_dir()} for item in islice(path.iterdir(), 500)]}
    if job.action == "read_file":
        path = _path(str(params.get("path", "")), allowed_roots)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("File is unavailable or exceeds the 1 MB limit")
        return {"content": path.read_text(encoding="utf-8")}
    if job.action == "write_file":
        path = _path(str(params.get("path", "")), allowed_roots)
        content = params.get("content")
        if not isinstance(content, str) or len(content.encode("utf-8")) > 1_000_000:
            raise ValueError("File content is invalid or exceeds the 1 MB limit")
        if not path.parent.is_dir():
            raise ValueError("Parent directory does not exist")
        path.write_text(content, encoding="utf-8")
        return {"bytes_written": len(content.encode("utf-8"))}
    command_key = params.get("command")
    argv = ALLOWED_COMMANDS.get(command_key) if isinstance(command_key, str) else None
    if argv is None:
        raise PermissionError("Command is not on the worker allowlist")
    if not allowed_roots:
        raise PermissionError("No worker command directory is configured")
    project_root = allowed_roots[0].resolve(strict=True)
    if command_key in {"python_tests", "npm_tests"}:
        return _run_project_tests(command_key, project_root)
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC"}}
    return _run_bounded(argv, cwd=str(project_root), env=environment)
