"""
Populate analytics.db with synthetic demo rows for local UI and dashboard tests.

Use when Clover sandbox credentials are not configured. Does not call the API.

WARNING: Deletes and repopulates rows in analytics.db (not reversible unless you
backed up the file). Not run by pytest. See docs/TESTING_STANDARDS.md.

Usage:
    python scripts/seed_demo_data.py
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.database import init_db, get_connection


def main():
    cfg = Config()
    init_db(cfg.DB_PATH)
    today = date.today()
    synced = f"{today.isoformat()}T12:00:00Z"

    with get_connection() as conn:
        conn.execute("DELETE FROM daily_sales")
        conn.execute("DELETE FROM stock_snapshots")
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM categories")

        conn.execute(
            """
            INSERT INTO categories (category_id, name, last_synced)
            VALUES ('cat-snacks', 'Snacks', ?),
                   ('cat-drinks', 'Drinks', ?)
            """,
            (synced, synced),
        )
        items = [
            ("item-001", "Bottled Water", 150, 50, "cat-drinks"),
            ("item-002", "Granola Bar", 200, 120, "cat-snacks"),
            ("item-003", "Chips", 175, 90, "cat-snacks"),
            ("item-004", "Energy Drink", 299, 180, "cat-drinks"),
        ]
        for item_id, name, price, cost, cat in items:
            conn.execute(
                """
                INSERT INTO items (item_id, name, price_cents, cost_cents, is_active, last_synced, category_id)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (item_id, name, price, cost, synced, cat),
            )

        for day_offset in range(90):
            sale_date = (today - timedelta(days=day_offset)).isoformat()
            for item_id, units, revenue in [
                ("item-001", 3 + day_offset % 5, (3 + day_offset % 5) * 150),
                ("item-002", 2 + day_offset % 3, (2 + day_offset % 3) * 200),
                ("item-003", 1 + day_offset % 4, (1 + day_offset % 4) * 175),
                ("item-004", day_offset % 2, day_offset % 2 * 299),
            ]:
                conn.execute(
                    """
                    INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item_id, sale_date, units, revenue),
                )

        for item_id, qty in [
            ("item-001", 48),
            ("item-002", 22),
            ("item-003", 15),
            ("item-004", 8),
        ]:
            conn.execute(
                """
                INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
                VALUES (?, ?, ?)
                """,
                (item_id, synced, qty),
            )

        conn.execute(
            """
            INSERT INTO sync_log (sync_ts, sync_type, records_fetched, status, error_detail)
            VALUES (?, 'demo', 0, 'success', NULL)
            """,
            (synced,),
        )

    print(f"Demo data written to {cfg.DB_PATH}")


if __name__ == "__main__":
    main()
