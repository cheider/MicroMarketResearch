"""
Shared date-range resolution for dashboards and analysis modules.
"""

from datetime import date, timedelta
import os

VALID_PERIODS = frozenset({
    "week", "lastweek", "7d", "30d", "90d", "semester",
})

_PERIOD_ALIASES = {
    "week": "7d",
    "lastweek": "lastweek",
}


def today() -> date:
    """Override in tests via monkeypatch for deterministic golden fixtures."""
    return date.today()


def normalize_period(period: str) -> str:
    p = (period or "week").strip().lower()
    if p in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[p]
    if p in VALID_PERIODS:
        return p
    if p.endswith("d") and p[:-1].isdigit():
        return p
    return "7d"


def _semester_start() -> date:
    env = os.environ.get("SEMESTER_START_DATE", "").strip()
    if env:
        return date.fromisoformat(env)
    try:
        from app.analysis.calendar import get_calendar_meta
        meta = get_calendar_meta()
        if meta.get("semester_start"):
            return date.fromisoformat(meta["semester_start"])
    except Exception:
        pass
    t = today()
    if t.month >= 8:
        return date(t.year, 8, 15)
    return date(t.year, 1, 10)


def resolve_period(period: str) -> dict:
    """
    Returns start_iso, end_iso, label, day_count for SQL filters.
    """
    p = normalize_period(period)
    end = today()

    if p == "lastweek":
        end = end - timedelta(days=7)
        start = end - timedelta(days=6)
        label = "Last 7 days (prior week)"
        day_count = 7
    elif p == "7d" or p == "week":
        start = end - timedelta(days=6)
        label = "Last 7 days"
        day_count = 7
    elif p == "30d":
        start = end - timedelta(days=29)
        label = "Last 30 days"
        day_count = 30
    elif p == "90d":
        start = end - timedelta(days=89)
        label = "Last 90 days"
        day_count = 90
    elif p == "semester":
        start = _semester_start()
        if start > end:
            start = end - timedelta(days=89)
        label = f"Semester (since {start.isoformat()})"
        day_count = (end - start).days + 1
    elif p.endswith("d") and p[:-1].isdigit():
        n = int(p[:-1])
        start = end - timedelta(days=n - 1)
        label = f"Last {n} days"
        day_count = n
    else:
        start = end - timedelta(days=6)
        label = "Last 7 days"
        day_count = 7
        p = "7d"

    return {
        "period": p,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": label,
        "day_count": day_count,
    }


def period_sql_days(period: str) -> int:
    """Lookback days for modules that use date('now', '-N days')."""
    return resolve_period(period)["day_count"]
