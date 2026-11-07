"""Package #179: calendar presentation must respect IANA timezones and DST.

This verifies user-visible calendar summaries without touching user data or
requiring native devices. It does not replace scheduling/worker acceptance.
"""
from orin_api.domain_router import _calendar_list_message


def _event(start: str, zone: str, end: str | None = None) -> dict[str, object]:
    return {"title": "Contract meeting", "start_at": start, "end_at": end,
            "timezone": zone, "is_all_day": False}


def test_calendar_summary_converts_utc_to_dar_es_salaam() -> None:
    summary = _calendar_list_message([_event("2026-11-07T09:00:00Z", "Africa/Dar_es_Salaam",
        "2026-11-07T10:00:00Z")])
    assert "12:00–13:00: Contract meeting" in summary


def test_calendar_summary_distinguishes_dst_fall_back_fold() -> None:
    first = _calendar_list_message([_event("2026-11-01T05:30:00Z", "America/New_York")])
    second = _calendar_list_message([_event("2026-11-01T06:30:00Z", "America/New_York")])
    # Two distinct instants both display as 01:30 locally during the fold.
    assert "01:30: Contract meeting" in first
    assert "01:30: Contract meeting" in second


def test_calendar_summary_handles_dst_spring_forward_gap() -> None:
    before = _calendar_list_message([_event("2027-03-14T06:30:00Z", "America/New_York")])
    after = _calendar_list_message([_event("2027-03-14T07:30:00Z", "America/New_York")])
    assert "01:30: Contract meeting" in before
    assert "03:30: Contract meeting" in after
    assert "02:30" not in before + after


def test_calendar_summary_invalid_timezone_fails_to_raw_instant() -> None:
    summary = _calendar_list_message([_event("2026-11-07T09:00:00Z", "Not/A_Zone")])
    assert "2026-11-07T09:00:00Z: Contract meeting" in summary
