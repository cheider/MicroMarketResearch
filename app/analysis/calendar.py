"""
Academic calendar: JSON term bounds, optional SQLite events, estimated exam weeks.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.analysis.term_schedule import (
    ESTIMATED_PREFIX,
    estimate_term_events,
    is_estimated_event_id,
)

_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "config" / "academic_calendar.json"


def _load_json_calendar() -> dict:
    if not _CALENDAR_PATH.exists():
        return {
            "term": "",
            "semester_start": None,
            "quarter_start": None,
            "quarter_end": None,
            "auto_estimate_events": True,
            "events": [],
        }
    with open(_CALENDAR_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # backward compat: semester_start only
    if not data.get("quarter_start") and data.get("semester_start"):
        data["quarter_start"] = data["semester_start"]
    return data


def save_calendar_json(
    term: str,
    quarter_start: str,
    quarter_end: str,
    auto_estimate_events: bool = True,
) -> None:
    data = _load_json_calendar()
    data["term"] = term
    data["quarter_start"] = quarter_start
    data["quarter_end"] = quarter_end
    data["semester_start"] = quarter_start
    data["auto_estimate_events"] = auto_estimate_events
    with open(_CALENDAR_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _load_db_events() -> list:
    try:
        from app.database import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT event_id AS id, label, start_date AS start, end_date AS end,
                       event_type AS type
                FROM academic_events
                ORDER BY start_date
                """
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_term_bounds() -> tuple[date | None, date | None]:
    meta = _load_json_calendar()
    qs = meta.get("quarter_start")
    qe = meta.get("quarter_end")
    start = date.fromisoformat(qs) if qs else None
    end = date.fromisoformat(qe) if qe else None
    return start, end


def _computed_estimated_events(data: dict) -> list:
    if not data.get("auto_estimate_events", True):
        return []
    qs, qe = get_term_bounds()
    if not qs or not qe:
        return []
    try:
        return estimate_term_events(qs, qe, data.get("term", ""))
    except ValueError:
        return []


def get_calendar_meta() -> dict:
    data = _load_json_calendar()
    db_events = _load_db_events()
    manual_db = [e for e in db_events if not is_estimated_event_id(e.get("id", ""))]
    estimated_db = [e for e in db_events if is_estimated_event_id(e.get("id", ""))]
    estimated = estimated_db or _computed_estimated_events(data)

    if manual_db or estimated_db:
        events = manual_db + estimated
    elif estimated:
        events = estimated
    else:
        events = data.get("events", [])

    events = sorted(events, key=lambda e: e.get("start", ""))

    return {
        "term": data.get("term", ""),
        "semester_start": data.get("quarter_start") or data.get("semester_start"),
        "quarter_start": data.get("quarter_start"),
        "quarter_end": data.get("quarter_end"),
        "auto_estimate_events": data.get("auto_estimate_events", True),
        "events": events,
        "estimated_preview": _computed_estimated_events(data),
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


def sync_estimated_events_to_db() -> list[dict]:
    """Replace estimated_* rows in SQLite from current quarter bounds in JSON."""
    meta = _load_json_calendar()
    qs = meta.get("quarter_start")
    qe = meta.get("quarter_end")
    if not qs or not qe:
        raise ValueError("Set quarter start and end dates first")

    start = date.fromisoformat(qs)
    end = date.fromisoformat(qe)
    estimated = estimate_term_events(start, end, meta.get("term", ""))

    from app.database import get_connection

    now = datetime.now(tz=timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM academic_events WHERE event_id LIKE ?",
            (f"{ESTIMATED_PREFIX}%",),
        )
        for ev in estimated:
            conn.execute(
                """
                INSERT INTO academic_events
                (event_id, label, start_date, end_date, event_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ev["id"], ev["label"], ev["start"], ev["end"], ev["type"], now),
            )
    return estimated


def upsert_academic_event(
    event_id: str, label: str, start_date: str, end_date: str, event_type: str
) -> None:
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
