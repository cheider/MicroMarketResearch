"""
Estimate midterm, break, and finals windows from quarter/term start and end dates.

Heuristic (adjust in Settings if your campus differs):
- Midterm 1: week centered at ~35% through the term
- Study break: week centered at ~50%
- Midterm 2: week centered at ~65%
- Finals: Mon–Fri of the week that contains the term end date
"""

from datetime import date, timedelta

ESTIMATED_PREFIX = "estimated_"


def _week_mon_fri(anchor: date) -> tuple[str, str]:
    monday = anchor - timedelta(days=anchor.weekday())
    friday = monday + timedelta(days=4)
    return monday.isoformat(), friday.isoformat()


def estimate_term_events(term_start: date, term_end: date, term_label: str = "") -> list[dict]:
    if term_end < term_start:
        raise ValueError("Term end must be on or after term start")

    span_days = (term_end - term_start).days
    if span_days < 14:
        raise ValueError("Term must be at least 14 days long")

    def _anchor(fraction: float) -> date:
        return term_start + timedelta(days=int(span_days * fraction))

    events = [
        {
            "id": f"{ESTIMATED_PREFIX}midterm_1",
            "label": "Midterm week 1 (estimated)",
            "start": _week_mon_fri(_anchor(0.35))[0],
            "end": _week_mon_fri(_anchor(0.35))[1],
            "type": "midterm",
            "estimated": True,
        },
        {
            "id": f"{ESTIMATED_PREFIX}break",
            "label": "Study break (estimated)",
            "start": _week_mon_fri(_anchor(0.50))[0],
            "end": _week_mon_fri(_anchor(0.50))[1],
            "type": "break",
            "estimated": True,
        },
        {
            "id": f"{ESTIMATED_PREFIX}midterm_2",
            "label": "Midterm week 2 (estimated)",
            "start": _week_mon_fri(_anchor(0.65))[0],
            "end": _week_mon_fri(_anchor(0.65))[1],
            "type": "midterm",
            "estimated": True,
        },
        {
            "id": f"{ESTIMATED_PREFIX}finals",
            "label": "Finals week (estimated)",
            "start": _week_mon_fri(term_end)[0],
            "end": _week_mon_fri(term_end)[1],
            "type": "finals",
            "estimated": True,
        },
    ]
    if term_label:
        for ev in events:
            ev["label"] = f"{ev['label']} — {term_label}"
    return events


def is_estimated_event_id(event_id: str) -> bool:
    return (event_id or "").startswith(ESTIMATED_PREFIX)
