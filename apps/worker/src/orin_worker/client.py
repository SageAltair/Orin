"""Authenticated worker polling and durable duplicate suppression."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import platform
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from orin_worker.capabilities import WorkerJob, execute_job

logger = logging.getLogger(__name__)


class JobLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.execute("CREATE TABLE IF NOT EXISTS handled_jobs (job_id TEXT PRIMARY KEY, status TEXT NOT NULL, result TEXT)")
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(handled_jobs)")}
        if "result" not in columns:
            self.connection.execute("ALTER TABLE handled_jobs ADD COLUMN result TEXT")
        self.connection.commit()

    def start_once(self, job_id: str) -> bool:
        try:
            self.connection.execute("INSERT INTO handled_jobs(job_id, status, result) VALUES (?, 'failed_pending', NULL)", (job_id,))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def save_outcome(self, job_id: str, status: str, result: dict[str, Any] | None) -> None:
        encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=True) if result is not None else None
        self.connection.execute("UPDATE handled_jobs SET status = ?, result = ? WHERE job_id = ?", (status, encoded, job_id))
        self.connection.commit()

    def mark_started(self, job_id: str) -> None:
        self.connection.execute("UPDATE handled_jobs SET status = 'started' WHERE job_id = ?", (job_id,))
        self.connection.commit()

    def pending_results(self) -> list[tuple[str, str, dict[str, Any] | None]]:
        rows = self.connection.execute("SELECT job_id, status, result FROM handled_jobs WHERE status IN ('completed_pending', 'failed_pending')").fetchall()
        return [(job_id, status, json.loads(result) if result else None) for job_id, status, result in rows]

    def mark_reported(self, job_id: str) -> None:
        self.connection.execute("UPDATE handled_jobs SET status = 'reported' WHERE job_id = ?", (job_id,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def _verify_signed(envelope: dict[str, Any], credential: str) -> WorkerJob:
    payload = envelope.get("payload")
    signature = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise ValueError("Malformed signed job")
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected = hmac.new(credential.encode(), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Worker job signature is invalid")
    return WorkerJob.model_validate(payload)


def _api_url_is_secure(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})


def execute_signed_job(envelope: dict[str, Any], *, credential: str, device_id: str,
                       allowed_roots: tuple[Path, ...], now: int) -> dict[str, Any]:
    job = _verify_signed(envelope, credential)
    if job.device_id != device_id:
        raise PermissionError("Signed job is assigned to another device")
    return execute_job(job, device_id=device_id, allowed_roots=allowed_roots, now=now)


def worker_loop(stopping: threading.Event) -> None:
    base_url = os.environ.get("ORIN_API_URL", "").rstrip("/")
    device_id = os.environ.get("ORIN_DEVICE_ID", "")
    credential = os.environ.get("ORIN_WORKER_TOKEN", "")
    if not base_url or not device_id or len(credential) < 32:
        raise RuntimeError("Set ORIN_API_URL, ORIN_DEVICE_ID, and the one-time ORIN_WORKER_TOKEN")
    if not _api_url_is_secure(base_url):
        raise RuntimeError("Worker API URL must use HTTPS outside localhost")
    roots = tuple(Path(item).expanduser().resolve() for item in os.environ.get("ORIN_ALLOWED_ROOTS", "").split(os.pathsep) if item.strip())
    ledger_path = Path(os.environ.get("ORIN_WORKER_STATE_PATH", Path.home() / ".orin" / "worker.sqlite3"))
    ledger = JobLedger(ledger_path)
    backoff = 1
    timeout = httpx.Timeout(20, connect=10)
    try:
        with httpx.Client(base_url=base_url + "/api/v1", headers={"Authorization": f"Bearer {credential}"}, timeout=timeout, follow_redirects=False) as client:
            while not stopping.is_set():
                try:
                    for pending_id, pending_status, pending_result in ledger.pending_results():
                        event_status = "completed" if pending_status == "completed_pending" else "failed"
                        try:
                            response = client.post(f"/worker/jobs/{pending_id}/event", json={"status": event_status, "result": pending_result})
                            response.raise_for_status()
                        except httpx.HTTPStatusError as event_error:
                            if event_error.response.status_code not in {404, 409}:
                                raise
                        ledger.mark_reported(pending_id)
                    client.post("/worker/heartbeat", headers={"X-Worker-Platform": platform.platform()[:80], "X-Worker-Version": os.getenv("ORIN_WORKER_VERSION", "0.1.0")}).raise_for_status()
                    claim = client.post("/worker/jobs/claim")
                    claim.raise_for_status()
                    envelope = claim.json()
                    if not envelope:
                        stopping.wait(2)
                        backoff = 1
                        continue
                    job = _verify_signed(envelope, credential)
                    if job.device_id != device_id:
                        raise ValueError("Signed job is assigned to another device")
                    if not ledger.start_once(job.job_id):
                        logger.warning("Worker refused a replayed job")
                        continue
                    client.post(f"/worker/jobs/{job.job_id}/event", json={"status": "starting", "message": "Validating approved work"}).raise_for_status()
                    client.post(f"/worker/jobs/{job.job_id}/event", json={"status": "running", "message": "Running an allowed capability"}).raise_for_status()
                    ledger.mark_started(job.job_id)
                    try:
                        result = execute_job(job, device_id=device_id, allowed_roots=roots, now=int(time.time()))
                    except Exception:
                        ledger.save_outcome(job.job_id, "failed_pending", None)
                        client.post(f"/worker/jobs/{job.job_id}/event", json={"status": "failed", "message": "Worker action failed"}).raise_for_status()
                        ledger.mark_reported(job.job_id)
                    else:
                        ledger.save_outcome(job.job_id, "completed_pending", result)
                        client.post(f"/worker/jobs/{job.job_id}/event", json={"status": "completed", "result": result}).raise_for_status()
                        ledger.mark_reported(job.job_id)
                    backoff = 1
                except httpx.HTTPStatusError as error:
                    if error.response.status_code in {401, 403}:
                        logger.error("Worker was rejected by the gateway; check device registration")
                        return
                    logger.warning("Worker gateway unavailable; retrying")
                    stopping.wait(backoff)
                    backoff = min(backoff * 2, 30)
                except (httpx.HTTPError, ValueError, KeyError):
                    # Do not put exception text, headers, payloads, or credentials in logs.
                    logger.warning("Worker gateway unavailable or returned an invalid job; retrying")
                    stopping.wait(backoff)
                    backoff = min(backoff * 2, 30)
    finally:
        ledger.close()
