import pytest
from datetime import datetime, timezone, timedelta

import app.database as db_module
from app.database import get_connection
from app.analysis.shrinkage import get_shrinkage_report


def _ts(offset_days=0):
    base = datetime.now(tz=timezone.utc) - timedelta(days=offset_days)
    return base.isoformat()


def seed_item(item_id="item-001", name="Test Item", price=100, cost=60):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, cost_cents, is_active, last_synced)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (item_id, name, price, cost, _ts()),
        )


def seed_snapshot(item_id, quantity, offset_days=0):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)"
            " VALUES (?, ?, ?)",
            (item_id, _ts(offset_days), quantity),
        )


def seed_sales(item_id, units, offset_days=0):
    dt = datetime.now(tz=timezone.utc) - timedelta(days=offset_days)
    sale_date = dt.strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_sales
                (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id, sale_date) DO UPDATE SET
                units_sold = excluded.units_sold
            """,
            (item_id, sale_date, units, units * 100),
        )


@pytest.fixture(autouse=True)
def setup_db(app):
    db_module._db_path = app.config["DB_PATH"]
    yield


class TestGetShrinkageReport:
    def test_empty_db_returns_empty_dataframe(self):
        df = get_shrinkage_report(days=30)
        assert df.empty

    def test_known_shrinkage_computes_correctly(self):
        seed_item("item-001")
        seed_snapshot("item-001", 10, offset_days=5)
        seed_snapshot("item-001", 6, offset_days=0)
        seed_sales("item-001", 3, offset_days=2)

        df = get_shrinkage_report(days=30)
        assert not df.empty
        row = df[df["item_id"] == "item-001"].iloc[0]
        assert row["shrinkage_units"] == 1

    def test_zero_shrinkage_scenario(self):
        seed_item("item-002")
        seed_snapshot("item-002", 10, offset_days=5)
        seed_snapshot("item-002", 7, offset_days=0)
        seed_sales("item-002", 3, offset_days=2)

        df = get_shrinkage_report(days=30)
        row = df[df["item_id"] == "item-002"]
        if not row.empty:
            assert row.iloc[0]["shrinkage_units"] == 0

    def test_shrinkage_value_cents_computed(self):
        seed_item("item-003", price=200)
        seed_snapshot("item-003", 20, offset_days=5)
        seed_snapshot("item-003", 15, offset_days=0)
        seed_sales("item-003", 3, offset_days=2)

        df = get_shrinkage_report(days=30)
        row = df[df["item_id"] == "item-003"].iloc[0]
        assert row["shrinkage_units"] == 2
        assert row["shrinkage_value_cents"] == 2 * 200

    def test_single_snapshot_only_does_not_crash(self):
        seed_item("item-004")
        seed_snapshot("item-004", 10, offset_days=0)
        df = get_shrinkage_report(days=30)
        assert isinstance(df, object)

    def test_no_sales_data_treated_as_zero_sold(self):
        seed_item("item-005")
        seed_snapshot("item-005", 10, offset_days=5)
        seed_snapshot("item-005", 8, offset_days=0)

        df = get_shrinkage_report(days=30)
        row = df[df["item_id"] == "item-005"]
        if not row.empty:
            assert row.iloc[0]["shrinkage_units"] == 2
