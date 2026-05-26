"""Shared DB seeding for analytics tests."""

from datetime import date, timedelta

import app.database as db_module
from app.database import get_connection


def seed_demo_pattern(anchor: date):
    synced = f"{anchor.isoformat()}T12:00:00Z"
    with get_connection() as conn:
        conn.execute("DELETE FROM daily_sales")
        conn.execute("DELETE FROM stock_snapshots")
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM categories")
        conn.execute("DELETE FROM academic_events")

        conn.execute(
            """
            INSERT INTO categories (category_id, name, last_synced)
            VALUES ('cat-snacks', 'Snacks', ?), ('cat-drinks', 'Drinks', ?)
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
            sale_date = (anchor - timedelta(days=day_offset)).isoformat()
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


def bind_test_db(app):
    db_module._db_path = app.config["DB_PATH"]
