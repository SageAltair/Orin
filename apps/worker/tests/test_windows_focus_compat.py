"""Legacy API compatibility checks: fail closed if Focus history is incomplete."""
import httpx
import pytest
from orin_worker.windows_reminders import _focus_active


def client(rows, status=405):
    def handler(req):
        if req.url.path.endswith('/focus-sessions/active'):
            return httpx.Response(status, json={'active': False})
        if req.url.path.endswith('/focus-sessions'):
            return httpx.Response(200, json=rows)
        return httpx.Response(404)
    return httpx.Client(base_url='http://localhost/api/v1',transport=httpx.MockTransport(handler))


def test_legacy_empty_history_allows_reminder():
    with client([]) as c:
        assert _focus_active(c) is False


def test_legacy_active_focus_suppresses_reminder():
    with client([{'status':'active'}]) as c:
        assert _focus_active(c) is True


def test_legacy_history_at_limit_fails_closed():
    with client([{'status':'completed'}]*50) as c:
        with pytest.raises(ValueError): _focus_active(c)


def test_legacy_malformed_history_fails_closed():
    with client([{'status':'unknown'}]) as c:
        with pytest.raises(ValueError): _focus_active(c)


@pytest.mark.parametrize('state', ['paused', 'expired', 'completed', 'cancelled'])
def test_legacy_real_nonactive_statuses(state):
    with client([{'status':state}]) as c:
        assert _focus_active(c) is False


def test_new_api_still_authoritative():
    with client([],status=200) as c:
        assert _focus_active(c) is False
