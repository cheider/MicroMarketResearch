"""
Academic calendar: JSON file first, SQLite academic_events when populated.
"""

import json
import os
from datetime import date
from pathlib import Path

_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "config" / "academic_calendar.json"


def _load_json_calendar() -> dict:
    if not _CALENDAR_PATH.exists():
        return {"term": "", "semester_start": None, "events": []}
    with open(_CALENDAR_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_db_events() -> list:
    try:
        from app.database import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT event_id AS id, label, start_date AS start, end_date AS end, event_type AS type
                FROM academic_events
                ORDER BY start_date
                """
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_calendar_meta() -> dict:
    data = _load_json_calendar()
    db_events = _load_db_events()
    events = db_events if db_events else data.get("events", [])
    return {
        "term": data.get("term", ""),
        "semester_start": data.get("semester_start"),
        "events": events,
    }


def get_all_events() -> list:
    return get_calendar_meta()["events"]


def get_event_by_id(event_id: str) -> dict | None:
    for ev in get_all_events():
        if ev.get("id") == event_id:
            return ev
    return None


def event_date_range(event: dict) -> tuple[str, str]:
    return event["start"], event["end"]


def events_on_date(d: date | None = None) -> list:
    d = d or date.today()
    iso = d.isoformat()
    active = []
    for ev in get_all_events():
        if ev.get("start") <= iso <= ev.get("end"):
            active.append(ev)
    return active


def upsert_academic_event(event_id: str, label: str, start_date: str, end_date: str, event_type: str) -> None:
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc).isoformat()
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO academic_events (event_id, label, start_date, end_date, event_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                label = excluded.label,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                event_type = excluded.event_type
            """,
            (event_id, label, start_date, end_date, event_type, now),
        )


def delete_academic_event(event_id: str) -> None:
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM academic_events WHERE event_id = ?", (event_id,))
