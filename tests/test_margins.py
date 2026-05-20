import pytest

import app.database as db_module
from app.database import get_connection
from app.analysis.margins import get_margin_report, get_item_margin


def seed_items(items):
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO items (item_id, name, price_cents, cost_cents, is_active, last_synced)
            VALUES (:item_id, :name, :price_cents, :cost_cents, :is_active, :last_synced)
            """,
            items,
        )


@pytest.fixture(autouse=True)
def setup_db(app):
    db_module._db_path = app.config["DB_PATH"]
    yield


class TestGetMarginReport:
    def test_empty_db_returns_empty_dataframes(self):
        report = get_margin_report()
        assert len(report["negative"]) == 0
        assert len(report["low"]) == 0
        assert len(report["acceptable"]) == 0

    def test_item_above_threshold_goes_to_acceptable(self):
        seed_items([{
            "item_id": "a", "name": "Good Item",
            "price_cents": 100, "cost_cents": 80,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        report = get_margin_report(threshold=0.10)
        assert len(report["acceptable"]) == 1
        assert len(report["negative"]) == 0
        assert len(report["low"]) == 0

    def test_item_below_threshold_goes_to_low(self):
        seed_items([{
            "item_id": "b", "name": "Thin Margin",
            "price_cents": 100, "cost_cents": 95,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        report = get_margin_report(threshold=0.10)
        assert len(report["low"]) == 1
        assert report["low"].iloc[0]["margin_pct"] == 5.0

    def test_item_below_cost_goes_to_negative(self):
        seed_items([{
            "item_id": "c", "name": "Loss Item",
            "price_cents": 100, "cost_cents": 110,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        report = get_margin_report(threshold=0.10)
        assert len(report["negative"]) == 1
        assert report["negative"].iloc[0]["margin_pct"] < 0

    def test_item_with_null_cost_goes_to_no_cost(self):
        seed_items([{
            "item_id": "d", "name": "No Cost",
            "price_cents": 100, "cost_cents": None,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        report = get_margin_report(threshold=0.10)
        assert len(report["no_cost"]) == 1
        assert len(report["acceptable"]) == 0

    def test_margin_calculation_accuracy(self):
        seed_items([{
            "item_id": "e", "name": "Math Check",
            "price_cents": 200, "cost_cents": 160,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        report = get_margin_report()
        row = report["acceptable"].iloc[0]
        assert row["margin_pct"] == 20.0


class TestGetItemMargin:
    def test_returns_none_for_unknown_item(self):
        result = get_item_margin("nonexistent")
        assert result is None

    def test_returns_margin_for_known_item(self):
        seed_items([{
            "item_id": "f", "name": "Single Item",
            "price_cents": 100, "cost_cents": 60,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        result = get_item_margin("f")
        assert result is not None
        assert result["margin_pct"] == 40.0

    def test_margin_none_when_no_cost(self):
        seed_items([{
            "item_id": "g", "name": "No Cost Item",
            "price_cents": 100, "cost_cents": None,
            "is_active": 1, "last_synced": "2025-01-01T00:00:00",
        }])
        result = get_item_margin("g")
        assert result["margin"] is None
        assert result["margin_pct"] is None
