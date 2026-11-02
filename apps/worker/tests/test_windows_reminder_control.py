"""Disposable loopback revocation contract. No OS notifications or real credentials."""
import hashlib
import hmac
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from orin_worker.windows_reminder_control import LocalRevocationControl
from orin_worker.windows_reminders import _notify_if_active

SESSION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
GENERATION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ORIGIN = "http://localhost:5273"


@pytest.fixture
def control():
    stopping = threading.Event()
    lock = threading.Lock()
    with LocalRevocationControl(
        session_id=SESSION, generation=GENERATION, allowed_origin=ORIGIN,
        stopping=stopping, delivery_lock=lock, port=0,
    ) as listener:
        yield listener, stopping, lock


def send(listener, method, path, *, origin=ORIGIN, body=None, host=None):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Origin": origin, "X-Orin-Reminder-Control": "1"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if host is not None:
        headers["Host"] = host
    request = Request(
        f"http://127.0.0.1:{listener.port}{path}", data=payload,
        method=method, headers=headers,
    )
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def challenge(listener):
    status, body = send(listener, "GET", "/challenge")
    assert status == 200
    return json.loads(body)["nonce"]


def proof(nonce):
    return hmac.new(GENERATION.encode(), f"{nonce}|{SESSION}".encode(), hashlib.sha256).hexdigest()


def test_authorized_browser_can_revoke_without_sending_generation(control):
    listener, stopping, _ = control
    nonce = challenge(listener)
    body = {"nonce": nonce, "session_id": SESSION, "proof": proof(nonce)}
    status, _ = send(listener, "POST", "/revoke", body=body)
    assert status == 204
    assert stopping.is_set()
    assert GENERATION not in json.dumps(body)


def test_wrong_origin_cannot_get_challenge_or_stop(control):
    listener, stopping, _ = control
    assert send(listener, "GET", "/challenge", origin="https://attacker.example")[0] == 403
    nonce = challenge(listener)
    assert send(listener, "POST", "/revoke", origin="https://attacker.example",
                body={"nonce": nonce, "session_id": SESSION, "proof": proof(nonce)})[0] == 403
    assert not stopping.is_set()


def test_wrong_generation_proof_and_replay_fail_closed(control):
    listener, stopping, _ = control
    nonce = challenge(listener)
    bad = hmac.new(b"wrong-generation", f"{nonce}|{SESSION}".encode(), hashlib.sha256).hexdigest()
    assert send(listener, "POST", "/revoke",
                body={"nonce": nonce, "session_id": SESSION, "proof": bad})[0] == 403
    assert not stopping.is_set()
    fresh = challenge(listener)
    body = {"nonce": fresh, "session_id": SESSION, "proof": proof(fresh)}
    assert send(listener, "POST", "/revoke", body=body)[0] == 204
    assert send(listener, "POST", "/revoke", body=body)[0] == 403


def test_wrong_session_and_host_rejected(control):
    listener, stopping, _ = control
    assert send(listener, "GET", "/challenge", host="attacker.example")[0] == 403
    nonce = challenge(listener)
    assert send(listener, "POST", "/revoke",
                body={"nonce": nonce, "session_id": "other", "proof": proof(nonce)})[0] == 403
    assert not stopping.is_set()


def test_preflight_only_for_trusted_origin(control):
    listener, _, _ = control
    assert send(listener, "OPTIONS", "/revoke")[0] == 204
    assert send(listener, "OPTIONS", "/revoke", origin="https://attacker.example")[0] == 403


def test_stop_event_suppresses_inflight_toast_before_delivery():
    stopping = threading.Event()
    lock = threading.Lock()
    notified = []
    stopping.set()
    assert _notify_if_active(lambda: notified.append(1), stopping, lock) is False
    assert notified == []


def test_port_collision_fails_instead_of_silently_disabling_control(control):
    listener, _, _ = control
    with pytest.raises(OSError):
        with LocalRevocationControl(
            session_id=SESSION, generation=GENERATION, allowed_origin=ORIGIN,
            stopping=threading.Event(), delivery_lock=threading.Lock(),
            port=listener.port,
        ):
            pass


@pytest.mark.parametrize("origin", [
    "http://evil.example",
    "http://127.0.0.1:4173/extra",
    "https://user:pass@example.com",
    "http://127.0.0.1:0",
    "file://localhost",
])
def test_untrusted_origin_fails_startup(origin):
    with pytest.raises(ValueError):
        LocalRevocationControl(
            session_id=SESSION, generation=GENERATION, allowed_origin=origin,
            stopping=threading.Event(), delivery_lock=threading.Lock(), port=0,
        )


def test_acknowledged_stop_waits_for_inflight_native_submission(control):
    listener, stopping, lock = control
    entered = threading.Event()
    release = threading.Event()
    notified = []
    responses = []

    def fake_notify():
        entered.set()
        assert release.wait(2)
        notified.append(1)

    notify_thread = threading.Thread(
        target=lambda: _notify_if_active(fake_notify, stopping, lock))
    notify_thread.start()
    assert entered.wait(2)
    nonce = challenge(listener)
    body = {"nonce": nonce, "session_id": SESSION, "proof": proof(nonce)}
    revoke_thread = threading.Thread(
        target=lambda: responses.append(send(listener, "POST", "/revoke", body=body)[0]))
    revoke_thread.start()
    # The stop acknowledgement cannot overtake a toast already being sent.
    assert not stopping.is_set()
    release.set()
    notify_thread.join(timeout=2)
    revoke_thread.join(timeout=2)
    assert notified == [1]
    assert responses == [204]
    assert stopping.is_set()
    # After acknowledgement, another toast must not be submitted.
    assert _notify_if_active(lambda: notified.append(2), stopping, lock) is False
    assert notified == [1]


def heartbeat_proof(nonce):
    return hmac.new(GENERATION.encode(), f"{nonce}|{SESSION}|heartbeat".encode(), hashlib.sha256).hexdigest()


def test_unreachable_browser_fails_closed_before_toast(control):
    listener, stopping, lock = control
    notified = []
    assert not listener.is_browser_recent()
    assert _notify_if_active(lambda: notified.append(1), stopping, lock,
                             delivery_permitted=listener.is_browser_recent) is False
    assert notified == []
    nonce = challenge(listener)
    payload = {"nonce": nonce, "session_id": SESSION, "proof": heartbeat_proof(nonce)}
    assert send(listener, "POST", "/heartbeat", body=payload)[0] == 204
    assert listener.is_browser_recent()
    assert _notify_if_active(lambda: notified.append(2), stopping, lock,
                             delivery_permitted=listener.is_browser_recent) is True
    assert notified == [2]
    listener._last_heartbeat_wall -= 20
    assert not listener.is_browser_recent()
    listener._last_heartbeat_wall += 20
    listener._last_heartbeat -= 20
    assert not listener.is_browser_recent()
    assert _notify_if_active(lambda: notified.append(3), stopping, lock,
                             delivery_permitted=listener.is_browser_recent) is False
    assert notified == [2]


def test_local_heartbeat_rejects_wrong_origin_and_revoke_proof(control):
    listener, stopping, _ = control
    nonce = challenge(listener)
    assert send(listener, "POST", "/heartbeat", origin="https://attacker.example",
                body={"nonce": nonce, "session_id": SESSION,
                      "proof": heartbeat_proof(nonce)})[0] == 403
    assert send(listener, "POST", "/heartbeat",
                body={"nonce": nonce, "session_id": SESSION,
                      "proof": proof(nonce)})[0] == 403
    assert not listener.is_browser_recent()
    assert not stopping.is_set()


def test_live_loopback_heartbeat_gates_synthetic_api_sqlite_delivery(control, tmp_path):
    """An active server lease alone must never authorize a native submission."""
    from datetime import datetime, timezone
    import httpx
    from orin_worker.windows_reminders import ReminderLedger, run_once

    listener, stopping, lock = control
    owner = "16e447d8-27f9-4b0d-82be-3f0dbf2d899b"
    workspace = "65e77714-26ba-420b-99a4-54093a5ad36b"
    now = int(datetime(2026, 11, 2, 20, tzinfo=timezone.utc).timestamp())
    due = datetime.fromtimestamp(now + 60, timezone.utc).isoformat()
    expiry = datetime.fromtimestamp(now + 45, timezone.utc).isoformat()
    queue = ReminderLedger(tmp_path / "synthetic.sqlite3", owner, workspace)
    delivered = []
    task_reads = []

    def api_handler(request):
        path = request.url.path
        if path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": owner})
        if path.endswith("/auth/sessions"):
            return httpx.Response(200, json=[{"id": SESSION, "active": True, "revoked_at": None}])
        if path.endswith("/auth/reminder-lease/" + SESSION):
            return httpx.Response(200, json={"workspace_id": workspace,
                                             "generation_id": GENERATION, "expires_at": expiry})
        if path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={"enabled": True, "categories": ["tasks"],
                                             "quiet_enabled": False, "respect_focus": False,
                                             "timezone": "UTC", "quiet_start": "22:00",
                                             "quiet_end": "07:00"})
        if path.endswith("/tasks"):
            task_reads.append(path)
            return httpx.Response(200, json=[{"id": "synthetic-due", "owner_id": owner,
                                             "workspace_id": workspace, "status": "todo",
                                             "due_at": due}])
        return httpx.Response(404)

    with httpx.Client(base_url="http://127.0.0.1:8100/api/v1",
                      transport=httpx.MockTransport(api_handler)) as client:
        kwargs = dict(now=now, delivery_clock=lambda: now, notify=lambda: delivered.append(1),
                      browser_session_id=SESSION, browser_lease_generation=GENERATION,
                      stopping=stopping, delivery_lock=lock,
                      delivery_permitted=listener.is_browser_recent)
        assert run_once(client, queue, **kwargs) == 0
        assert delivered == []
        assert task_reads == [], "no private task reads without browser presence"
        nonce = challenge(listener)
        assert send(listener, "POST", "/heartbeat", body={
            "nonce": nonce, "session_id": SESSION, "proof": heartbeat_proof(nonce)})[0] == 204
        assert run_once(client, queue, **kwargs) == 1
        assert delivered == [1]
    queue.close()
