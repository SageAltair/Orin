"""Opt-in loopback kill switch for the foreground Windows reminder companion.

No bearer credentials, task contents, or persistent capabilities are exposed.
The current browser lease generation is the ephemeral HMAC key. This server
can only STOP delivery; it cannot start, schedule or retrieve notifications.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def _origin_allowed(origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        return (
            bool(parsed.hostname) and not parsed.username and not parsed.password
            and not parsed.path and not parsed.query and not parsed.fragment
            and origin == f"{parsed.scheme}://{parsed.netloc}"
            and (parsed.scheme == "https" or (
                parsed.scheme == "http" and parsed.hostname in
                {"localhost", "127.0.0.1", "::1"}
            ))
            and parsed.port != 0
        )
    except ValueError:
        return False


class _ExclusiveLoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        if os.name == "nt":
            # SO_REUSEADDR on Windows can permit a second process to hijack
            # the same port. Require an exclusive listener or fail startup.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class LocalRevocationControl:
    """Foreground-only, origin-restricted, generation-authenticated stop channel.

    A revocation acknowledgement is serialized against toast submission.
    Port collision or invalid configuration fails startup. A configured but
    unreachable browser cannot authorize delivery: each native submission
    requires an authenticated local heartbeat no older than six seconds.
    """

    def __init__(
        self, *, session_id: str, generation: str, allowed_origin: str,
        stopping: threading.Event, delivery_lock: threading.Lock,
        port: int = 18765,
    ):
        if not _origin_allowed(allowed_origin):
            raise ValueError("Invalid trusted browser origin for local reminder control")
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("Invalid local reminder control port")
        session_id = str(uuid.UUID(session_id))
        generation = str(uuid.UUID(generation))
        self._stopping = stopping
        self._delivery_lock = delivery_lock
        self._last_heartbeat = 0.0
        self._nonces: dict[str, float] = {}
        self._nonce_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                # Never log URL, Origin, session identifiers or HMAC proofs.
                pass

            def _authorized(self) -> bool:
                return (
                    self.headers.get("Host") == f"127.0.0.1:{owner.port}"
                    and self.headers.get("Origin") == allowed_origin
                    and self.headers.get("X-Orin-Reminder-Control") == "1"
                )

            def _response(self, status: int, payload: bytes = b"") -> None:
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                if self._authorized():
                    self.send_header("Access-Control-Allow-Origin", allowed_origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Access-Control-Allow-Private-Network", "true")
                if payload:
                    self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload:
                    self.wfile.write(payload)

            def do_OPTIONS(self) -> None:
                requested = self.headers.get("Access-Control-Request-Method")
                if (self.path not in {"/challenge", "/revoke", "/heartbeat"}
                        or self.headers.get("Host") != f"127.0.0.1:{owner.port}"
                        or self.headers.get("Origin") != allowed_origin
                        or requested not in {None, "GET", "POST"}):
                    self._response(403)
                    return
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Orin-Reminder-Control")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Vary", "Origin")
                self.end_headers()

            def do_GET(self) -> None:
                if self.path != "/challenge" or not self._authorized():
                    self._response(403)
                    return
                nonce = secrets.token_hex(16)
                with owner._nonce_lock:
                    now = time.monotonic()
                    owner._nonces = {key: expiry for key, expiry in owner._nonces.items()
                                     if expiry > now}
                    if len(owner._nonces) >= 64:
                        self._response(429)
                        return
                    owner._nonces[nonce] = now + 15
                self._response(200, json.dumps({"nonce": nonce}).encode())

            def do_POST(self) -> None:
                if self.path not in {"/revoke", "/heartbeat"} or not self._authorized():
                    self._response(403)
                    return
                length = self.headers.get("Content-Length", "")
                if (not length.isascii() or not length.isdecimal()
                        or not 1 <= int(length) <= 512
                        or self.headers.get("Content-Type", "").split(";")[0].strip()
                        != "application/json"):
                    self._response(400)
                    return
                try:
                    data = json.loads(self.rfile.read(int(length)))
                except (ValueError, UnicodeDecodeError):
                    self._response(400)
                    return
                if not isinstance(data, dict) or set(data) != {"nonce", "session_id", "proof"}:
                    self._response(403)
                    return
                nonce, session, proof = (data.get("nonce"), data.get("session_id"), data.get("proof"))
                if not all(isinstance(value, str) for value in (nonce, session, proof)):
                    self._response(403)
                    return
                if not re.fullmatch(r"[0-9a-f]{32}", nonce) or not re.fullmatch(r"[0-9a-f]{64}", proof):
                    self._response(403)
                    return
                with owner._nonce_lock:
                    expiry = owner._nonces.pop(nonce, 0)
                expected = hmac.new(
                    generation.encode(), f"{nonce}|{session_id}".encode() +
                    (b"|heartbeat" if self.path == "/heartbeat" else b""),
                    hashlib.sha256,
                ).hexdigest()
                if (expiry <= time.monotonic()
                        or not hmac.compare_digest(session, session_id)
                        or not hmac.compare_digest(proof, expected)):
                    self._response(403)
                    return
                # No successful response can race ahead of an already-started
                # toast. Once 204 is sent, the worker cannot submit another.
                with owner._delivery_lock:
                    if self.path == "/heartbeat":
                        if owner._stopping.is_set():
                            self._response(409)
                            return
                        owner._last_heartbeat = time.monotonic()
                    else:
                        owner._stopping.set()
                self._response(204)

        self._server = _ExclusiveLoopbackServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_port

    def is_browser_recent(self) -> bool:
        """Only allow foreground delivery after a recent authenticated browser pulse."""
        return (not self._stopping.is_set() and self._last_heartbeat > 0
                and time.monotonic() - self._last_heartbeat <= 6)

    def __enter__(self) -> "LocalRevocationControl":
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="orin-reminder-local-stop",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)
