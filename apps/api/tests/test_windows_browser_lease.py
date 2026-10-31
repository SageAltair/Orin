"""Regression: a workspace switch must invalidate the old Windows companion lease."""
import uuid

from test_auth import auth_client, register, login, authenticate


def test_workspace_switch_revokes_stale_lease(auth_client):
    browser = auth_client
    register(browser, "lease-owner@example.com")
    browser_access = login(browser, "lease-owner@example.com")
    authenticate(browser, str(browser_access["access_token"]))
    session_id = next(s["id"] for s in browser.get("/api/v1/auth/sessions").json() if s["current"])
    a = browser.post("/api/v1/workspaces", json={"name": "Lease A"}).json()["id"]
    b = browser.post("/api/v1/workspaces", json={"name": "Lease B"}).json()["id"]
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    endpoint = "/api/v1/auth/reminder-lease"
    created = browser.put(endpoint, json={"workspace_id": a, "generation_id": first, "rotate": True})
    assert created.status_code == 200, created.text
    assert created.json()["expires_at"].endswith("+00:00")
    companion_access = login(browser, "lease-owner@example.com")
    authenticate(browser, str(companion_access["access_token"]))
    read = browser.get(f"{endpoint}/{session_id}")
    assert read.status_code == 200, read.text
    assert read.json()["generation_id"] == first

    authenticate(browser, str(browser_access["access_token"]))
    switched = browser.put(endpoint, json={"workspace_id": b, "generation_id": second, "rotate": True})
    assert switched.status_code == 200, switched.text
    assert browser.put(endpoint, json={"workspace_id": a, "generation_id": first}).status_code == 409
    authenticate(browser, str(companion_access["access_token"]))
    after_switch = browser.get(f"{endpoint}/{session_id}")
    assert after_switch.status_code == 200
    assert after_switch.json()["workspace_id"] == b
    assert after_switch.json()["generation_id"] == second

    register(browser, "lease-other@example.com")
    other_access = login(browser, "lease-other@example.com")
    authenticate(browser, str(other_access["access_token"]))
    assert browser.get(f"{endpoint}/{session_id}").status_code == 404
    assert browser.put(endpoint, json={"workspace_id": a, "generation_id": str(uuid.uuid4()), "rotate": True}).status_code == 404

    authenticate(browser, str(browser_access["access_token"]))
    assert browser.post("/api/v1/auth/logout").status_code == 204
    authenticate(browser, str(companion_access["access_token"]))
    assert browser.get(f"{endpoint}/{session_id}").status_code == 404


def test_expired_lease_requires_new_generation(auth_client, monkeypatch):
    import orin_api.auth_router as auth_router
    browser = auth_client
    register(browser, "lease-expiry@example.com")
    access = login(browser, "lease-expiry@example.com")
    authenticate(browser, str(access["access_token"]))
    session_id = next(s["id"] for s in browser.get("/api/v1/auth/sessions").json() if s["current"])
    workspace = browser.post("/api/v1/workspaces", json={"name": "Expiry A"}).json()["id"]
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    endpoint = "/api/v1/auth/reminder-lease"
    monkeypatch.setattr(auth_router, "REMINDER_LEASE_SECONDS", -1)
    assert browser.put(endpoint, json={
        "workspace_id": workspace, "generation_id": first, "rotate": True,
    }).status_code == 200
    assert browser.get(f"{endpoint}/{session_id}").status_code == 404
    assert browser.put(endpoint, json={
        "workspace_id": workspace, "generation_id": first,
    }).status_code == 409
    monkeypatch.setattr(auth_router, "REMINDER_LEASE_SECONDS", 45)
    assert browser.put(endpoint, json={
        "workspace_id": workspace, "generation_id": second, "rotate": True,
    }).status_code == 200
    assert browser.get(f"{endpoint}/{session_id}").json()["generation_id"] == second


def test_stale_tab_close_cannot_revoke_newer_workspace_lease(auth_client):
    """Tab A's delayed pagehide must not delete tab B's newer lease."""
    browser = auth_client
    register(browser, "lease-tabs@example.com")
    access = login(browser, "lease-tabs@example.com")
    authenticate(browser, str(access["access_token"]))
    session_id = next(s["id"] for s in browser.get("/api/v1/auth/sessions").json() if s["current"])
    a = browser.post("/api/v1/workspaces", json={"name": "Tab A"}).json()["id"]
    b = browser.post("/api/v1/workspaces", json={"name": "Tab B"}).json()["id"]
    generation_a, generation_b = str(uuid.uuid4()), str(uuid.uuid4())
    endpoint = "/api/v1/auth/reminder-lease"
    assert browser.put(endpoint, json={"workspace_id": a, "generation_id": generation_a, "rotate": True}).status_code == 200
    assert browser.put(endpoint, json={"workspace_id": b, "generation_id": generation_b, "rotate": True}).status_code == 200
    # This is the request emitted by tab A after tab B has taken ownership.
    stale_revoke = browser.request("DELETE", endpoint, json={"generation_id": generation_a})
    assert stale_revoke.status_code == 409, stale_revoke.text
    current = browser.get(f"{endpoint}/{session_id}")
    assert current.status_code == 200, current.text
    assert current.json()["generation_id"] == generation_b
    assert browser.request("DELETE", endpoint, json={"generation_id": generation_b}).status_code == 204
    assert browser.get(f"{endpoint}/{session_id}").status_code == 404
    # Preserve the legacy explicit no-body revocation contract.
    assert browser.put(endpoint, json={
        "workspace_id": a, "generation_id": str(uuid.uuid4()), "rotate": True,
    }).status_code == 200
    assert browser.delete(endpoint).status_code == 204
    assert browser.get(f"{endpoint}/{session_id}").status_code == 404
