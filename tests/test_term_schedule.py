from datetime import date

import pytest

from app.analysis.term_schedule import estimate_term_events, is_estimated_event_id
from app.analysis.calendar import save_calendar_json, get_calendar_meta, sync_estimated_events_to_db


def test_estimate_term_events_order():
    start = date(2025, 8, 15)
    end = date(2025, 12, 20)
    events = estimate_term_events(start, end)
    assert len(events) == 4
    ids = [e["id"] for e in events]
    assert ids[0].startswith("estimated_")
    assert events[0]["start"] < events[-1]["start"]


def test_estimate_requires_min_length():
    with pytest.raises(ValueError):
        estimate_term_events(date(2025, 1, 1), date(2025, 1, 10))


def test_is_estimated_event_id():
    assert is_estimated_event_id("estimated_finals")
    assert not is_estimated_event_id("finals_2025")


def test_save_calendar_json_and_preview(tmp_path, monkeypatch):
    cal_path = tmp_path / "academic_calendar.json"
    monkeypatch.setattr("app.analysis.calendar._CALENDAR_PATH", cal_path)
    save_calendar_json("2026-spring", "2026-01-10", "2026-05-15", True)
    meta = get_calendar_meta()
    assert meta["quarter_start"] == "2026-01-10"
    assert len(meta["estimated_preview"]) == 4


def test_sync_estimated_events_to_db(app, tmp_path, monkeypatch):
    cal_path = tmp_path / "academic_calendar.json"
    monkeypatch.setattr("app.analysis.calendar._CALENDAR_PATH", cal_path)
    save_calendar_json("test", "2025-08-15", "2025-12-20", True)
    rows = sync_estimated_events_to_db()
    assert len(rows) == 4
    meta = get_calendar_meta()
    assert any(e["id"].startswith("estimated_") for e in meta["events"])
