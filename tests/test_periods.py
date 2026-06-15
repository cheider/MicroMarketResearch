from datetime import date

import pytest

import app.analysis.periods as periods
from app.analysis.periods import normalize_period, resolve_period

ANCHOR = date(2026, 5, 24)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: ANCHOR)


class TestPeriods:
    def test_normalize_week_to_7d(self):
        assert normalize_period("week") == "7d"

    def test_resolve_7d_span(self):
        info = resolve_period("7d")
        assert info["start"] == "2026-05-18"
        assert info["end"] == "2026-05-24"
        assert info["day_count"] == 7

    def test_resolve_30d_span(self):
        info = resolve_period("30d")
        assert info["day_count"] == 30

    def test_lastweek_prior_window(self):
        info = resolve_period("lastweek")
        assert info["end"] == "2026-05-17"
