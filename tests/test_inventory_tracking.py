"""Per-item inventory tracking flag."""

from app.database import get_connection, init_db
from app.analysis.dashboard_analytics import get_low_stock_items, get_inventory_stats
from app.analysis.projections import reorder_suggestions
from app.item_settings import set_item_track_inventory


def _seed_item(item_id: str, name: str, qty: int):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced, track_inventory)
            VALUES (?, ?, 100, 1, '2026-01-01', 1)
            """,
            (item_id, name),
        )
        conn.execute(
            """
            INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
            VALUES (?, '2026-06-01', ?)
            """,
            (item_id, qty),
        )


def test_untracked_item_excluded_from_low_stock(app):
    init_db(app.config["DB_PATH"])
    _seed_item("TRACKED", "Chips", 3)
    _seed_item("UNTRACKED", "Extra Shot", 0)
    set_item_track_inventory("UNTRACKED", False)

    rows = get_low_stock_items(threshold=10)
    names = [r["name"] for r in rows]
    assert "Chips" in names
    assert "Extra Shot" not in names


def test_untracked_item_excluded_from_low_stock_kpi(app):
    init_db(app.config["DB_PATH"])
    _seed_item("A", "Snack A", 2)
    _seed_item("B", "Latte Modifier", 0)
    set_item_track_inventory("B", False)

    stats = get_inventory_stats()
    assert stats["low_stock_count"] == 1


def test_untracked_item_excluded_from_reorder(app):
    init_db(app.config["DB_PATH"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced, track_inventory)
            VALUES ('MOD', 'Alt Milk', 0, 1, '2026-01-01', 0)
            """,
        )
        conn.execute(
            """
            INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
            VALUES ('MOD', '2026-06-01', 0)
            """,
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('MOD', '2026-05-20', 50, 0)
            """,
        )

    ids = [r["item_id"] for r in reorder_suggestions(min_avg_daily=0.01)]
    assert "MOD" not in ids
