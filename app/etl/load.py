"""
Writes cleaned, anonymized data into SQLite.
All rows arriving here have already passed through transform.py.
"""

from datetime import datetime, timezone

from app.database import get_connection


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def upsert_categories(categories: list):
    """Batch insert or update category rows."""
    now = _now_utc()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO categories (category_id, name, last_synced)
            VALUES (:category_id, :name, :last_synced)
            ON CONFLICT(category_id) DO UPDATE SET
                name        = excluded.name,
                last_synced = excluded.last_synced
            """,
            [
                {
                    "category_id": c["category_id"],
                    "name": c["name"],
                    "last_synced": now,
                }
                for c in categories
                if c.get("category_id")
            ],
        )


def upsert_item(item: dict):
    """Insert or update a single item row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, cost_cents, is_active, category_id, last_synced)
            VALUES
                (:item_id, :name, :price_cents, :cost_cents, :is_active, :category_id, :last_synced)
            ON CONFLICT(item_id) DO UPDATE SET
                name        = excluded.name,
                price_cents = excluded.price_cents,
                cost_cents  = excluded.cost_cents,
                is_active   = excluded.is_active,
                category_id = excluded.category_id,
                last_synced = excluded.last_synced
            """,
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "price_cents": item["price_cents"],
                "cost_cents": item.get("cost_cents"),
                "is_active": item.get("is_active", 1),
                "category_id": item.get("category_id"),
                "last_synced": _now_utc(),
            },
        )


def upsert_items(items: list):
    """Batch insert or update item rows."""
    now = _now_utc()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO items
                (item_id, name, price_cents, cost_cents, is_active, category_id, last_synced)
            VALUES
                (:item_id, :name, :price_cents, :cost_cents, :is_active, :category_id, :last_synced)
            ON CONFLICT(item_id) DO UPDATE SET
                name        = excluded.name,
                price_cents = excluded.price_cents,
                cost_cents  = excluded.cost_cents,
                is_active   = excluded.is_active,
                category_id = excluded.category_id,
                last_synced = excluded.last_synced
            """,
            [
                {
                    "item_id": item["item_id"],
                    "name": item["name"],
                    "price_cents": item["price_cents"],
                    "cost_cents": item.get("cost_cents"),
                    "category_id": item.get("category_id"),
                    "is_active": item.get("is_active", 1),
                    "last_synced": now,
                }
                for item in items
                if item.get("item_id")
            ],
        )


def upsert_daily_sales(sales_rows: list):
    """
    Insert or accumulate daily sales aggregates.
    Rows whose item_id has no matching item are silently dropped — Clover
    sometimes returns line items for items that the items endpoint omits
    (deleted or restricted items), which would cause a FK violation.
    """
    with get_connection() as conn:
        known_ids = {
            row[0]
            for row in conn.execute("SELECT item_id FROM items").fetchall()
        }
        valid_rows = [r for r in sales_rows if r["item_id"] in known_ids]
        if not valid_rows:
            return
        conn.executemany(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES (:item_id, :sale_date, :units_sold, :gross_revenue_cents)
            ON CONFLICT(item_id, sale_date) DO UPDATE SET
                units_sold          = excluded.units_sold,
                gross_revenue_cents = excluded.gross_revenue_cents
            """,
            valid_rows,
        )


def insert_stock_snapshot(stock: dict):
    """Insert a single stock snapshot. Snapshots are append-only."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
            VALUES (:item_id, :snapshot_ts, :quantity)
            """,
            {
                "item_id": stock["item_id"],
                "snapshot_ts": _now_utc(),
                "quantity": stock["quantity"],
            },
        )


def insert_stock_snapshots(stocks: list):
    """Batch insert stock snapshots. Snapshots are append-only."""
    now = _now_utc()
    with get_connection() as conn:
        known_ids = {
            row[0]
            for row in conn.execute("SELECT item_id FROM items").fetchall()
        }
        conn.executemany(
            """
            INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
            VALUES (:item_id, :snapshot_ts, :quantity)
            """,
            [
                {
                    "item_id": s["item_id"],
                    "snapshot_ts": now,
                    "quantity": s["quantity"],
                }
                for s in stocks
                if s.get("item_id") in known_ids
            ],
        )


def log_sync(sync_type: str, records_fetched: int, status: str, error_detail: str = None):
    """Write a sync_log entry."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sync_log (sync_ts, sync_type, records_fetched, status, error_detail)
            VALUES (:sync_ts, :sync_type, :records_fetched, :status, :error_detail)
            """,
            {
                "sync_ts": _now_utc(),
                "sync_type": sync_type,
                "records_fetched": records_fetched,
                "status": status,
                "error_detail": error_detail,
            },
        )


def get_last_successful_sync_ts() -> str | None:
    """Returns the ISO-8601 timestamp of the last successful sync, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT sync_ts FROM sync_log
            WHERE status = 'success'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return row["sync_ts"] if row else None


def upsert_fetched_orders(order_ids: list) -> None:
    """Record order IDs whose line items have been fetched (idempotent)."""
    if not order_ids:
        return
    now = _now_utc()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO fetched_orders (order_id, fetched_at)
            VALUES (?, ?)
            ON CONFLICT(order_id) DO NOTHING
            """,
            [(oid, now) for oid in order_ids],
        )


def get_fetched_order_ids() -> set:
    """Return the set of all order IDs already fetched."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT order_id FROM fetched_orders"
        ).fetchall()
    return {row["order_id"] for row in rows}
