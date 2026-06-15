import json
from datetime import date
from pathlib import Path

import pytest

import app.analysis.periods as periods
from app.analysis.dashboard_analytics import get_sales_stats
from app.analysis.projections import get_forecast_summary, reorder_suggestions
from tests.test_helpers import bind_test_db, seed_demo_pattern

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_demo_expectations.json"
ANCHOR = date(2026, 5, 24)


@pytest.fixture(autouse=True)
def setup_db(app):
    bind_test_db(app)
    seed_demo_pattern(ANCHOR)
    yield


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: ANCHOR)


def _load_golden():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestGoldenAnalytics:
    def test_sales_stats_7d_matches_fixture(self):
        golden = _load_golden()["period_7d"]
        stats = get_sales_stats(period="7d")
        assert stats["total_revenue_cents"] == golden["total_revenue_cents"]
        assert stats["units_sold"] == golden["units_sold"]
        assert stats["active_items"] == golden["active_items"]

    def test_sales_stats_30d_has_volume(self):
        golden = _load_golden()["period_30d"]
        stats = get_sales_stats(period="30d")
        assert stats["total_revenue_cents"] >= golden["min_total_revenue_cents"]

    def test_forecast_summary_positive(self):
        golden = _load_golden()["forecast"]
        summary = get_forecast_summary(horizon_days=14)
        assert summary["total_projected_revenue_cents"] >= golden["min_projected_revenue_cents"]

    def test_reorder_suggestions_populated(self):
        golden = _load_golden()["reorder"]
        rows = reorder_suggestions()
        assert len(rows) >= golden["min_suggestions"]
