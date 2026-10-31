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
