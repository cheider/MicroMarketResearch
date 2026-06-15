"""Dashboard routes with populated analytics data."""

from datetime import date

import pytest

import app.analysis.periods as periods
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


class TestDashboardsWithData:
    def test_sales_dashboard_shows_revenue(self, client):
        response = client.get("/dashboards/sales?period=7d")
        assert response.status_code == 200
        assert b"Total Revenue" in response.data

    def test_sales_dashboard_30d_period(self, client):
        response = client.get("/dashboards/sales?period=30d")
        assert response.status_code == 200

    def test_inventory_dashboard_returns_200(self, client):
        response = client.get("/dashboards/inventory")
        assert response.status_code == 200
        assert b"Turnover" in response.data or b"Stock" in response.data

    def test_profit_dashboard_returns_200(self, client):
        response = client.get("/dashboards/profit")
        assert response.status_code == 200
        assert b"Profit" in response.data

    def test_sales_download_csv(self, client):
        response = client.get("/dashboards/sales/download")
        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert b"item_id" in response.data
