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


def _term_bounds() -> tuple[date, date]:
    env_start = os.environ.get("SEMESTER_START_DATE", "").strip()
    env_end = os.environ.get("TERM_END_DATE", "").strip()
    try:
        from app.analysis.calendar import get_term_bounds

        qs, qe = get_term_bounds()
        if qs and qe:
            return qs, qe
        if qs:
            end = today()
            return qs, end if end >= qs else qs
    except Exception:
        pass
    if env_start:
        start = date.fromisoformat(env_start)
        if env_end:
            return start, date.fromisoformat(env_end)
        return start, today()
    t = today()
    if t.month >= 8:
        start = date(t.year, 8, 15)
    else:
        start = date(t.year, 1, 10)
    return start, t


def _semester_start() -> date:
    return _term_bounds()[0]


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
        start, term_end = _term_bounds()
        if start > end:
            start = end - timedelta(days=89)
        label = f"Term ({start.isoformat()} – {term_end.isoformat()})"
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
