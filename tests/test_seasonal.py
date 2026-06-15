from datetime import date

import pytest

import app.analysis.periods as periods
from app.analysis.seasonal import (
    get_day_of_week_profile,
    get_week_over_week,
    get_category_mix_shift,
)
from tests.test_helpers import bind_test_db, seed_demo_pattern

ANCHOR = date(2026, 5, 24)


@pytest.fixture(autouse=True)
def setup_db(app):
    bind_test_db(app)
    seed_demo_pattern(ANCHOR)
    yield


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: ANCHOR)


class TestSeasonalAnalytics:
    def test_day_of_week_profile_has_seven_days(self):
        profile = get_day_of_week_profile("30d")
        assert len(profile["labels"]) == 7
        assert len(profile["avg_revenue"]) == 7

    def test_week_over_week_has_change_pct(self):
        wow = get_week_over_week("7d")
        assert "revenue_change_pct" in wow
        assert wow["current_revenue_cents"] >= 0

    def test_category_mix_shift_returns_rows(self):
        mix = get_category_mix_shift("30d")
        assert len(mix) >= 1
        assert "share_shift_pct" in mix[0]
