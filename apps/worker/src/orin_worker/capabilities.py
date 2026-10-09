"""Fail-closed local worker capabilities. No shell strings or implicit filesystem roots."""
from __future__ import annotations

import os
import subprocess
import sys
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
}
ALLOWED_COMMANDS: dict[str, tuple[str, ...]] = {
    "git_status": ("git", "status", "--short"),
    "git_version": ("git", "--version"),
    "python_tests": (sys.executable, "-m", "pytest", "-q"),
    "npm_tests": ("npm", "test", "--", "--run"),
}

_PROTECTED_NAMES = {".ssh", ".aws", ".azure", ".config", "credentials", "secrets", "program files", "program files (x86)", "programdata", "windows", "id_rsa", "id_ed25519"}


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
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC"}}
    completed = subprocess.run(argv, cwd=str(project_root), env=environment,
        capture_output=True, text=True, timeout=120, check=False, shell=False)
    return {"return_code": completed.returncode, "stdout": completed.stdout[:4000], "stderr": completed.stderr[:1000]}
