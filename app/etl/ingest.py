"""
Orchestrates full and incremental ETL runs.

Flow:
  1. Fetch categories from Clover
  2. Transform and upsert categories
  3. Fetch items from Clover
  4. Transform (anonymize, filter fields)
  5. Upsert into SQLite
  6. Fetch orders for the target date range
  7. For each order, fetch line items
  8. Aggregate line items to daily totals in memory
  9. Upsert daily_sales into SQLite
  10. Fetch stock snapshots
  11. Insert stock_snapshots into SQLite
  12. Log sync result
"""

from datetime import datetime, timedelta, timezone

from app.clover.endpoints import (
    fetch_categories,
    fetch_items,
    fetch_orders,
    fetch_line_items,
    fetch_item_stocks,
)
from app.etl.transform import clean_category, clean_item, clean_stock, aggregate_line_items
from app.etl.load import (
    upsert_categories,
    upsert_items,
    upsert_daily_sales,
    insert_stock_snapshots,
    log_sync,
    get_last_successful_sync_ts,
)


def _date_range_ms(days_back: int) -> tuple[int, int]:
    """Returns (start_ms, end_ms) for a UTC window ending now."""
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=days_back)
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def _ts_to_ms(iso_ts: str) -> int:
    """Converts an ISO-8601 timestamp string to milliseconds since epoch."""
    dt = datetime.fromisoformat(iso_ts)
    return int(dt.timestamp() * 1000)


def run_full_ingest(client, days: int = 30) -> dict:
    """
    Pulls all items, orders, and stock for the past `days` days.
    Returns a summary dict with counts and status.
    """
    return _run_ingest(client, mode="full", days=days)


def run_incremental_ingest(client, days: int = 30) -> dict:
    """
    Pulls data since the last successful sync.
    Falls back to a full ingest if no prior sync exists.
    """
    last_sync = get_last_successful_sync_ts()
    if not last_sync:
        return run_full_ingest(client, days=days)
    return _run_ingest(client, mode="incremental", days=days, since_ts=last_sync)


def _run_ingest(client, mode: str, days: int, since_ts: str = None) -> dict:
    records_fetched = 0
    try:
        raw_categories = fetch_categories(client)
        clean_cats = [clean_category(r) for r in raw_categories]
        clean_cats = [c for c in clean_cats if c.get("category_id")]
        upsert_categories(clean_cats)
        records_fetched += len(clean_cats)

        raw_items = fetch_items(client)
        clean_items = [clean_item(r) for r in raw_items]
        clean_items = [i for i in clean_items if i.get("item_id")]
        upsert_items(clean_items)
        records_fetched += len(clean_items)

        if since_ts:
            start_ms = _ts_to_ms(since_ts)
            end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        else:
            start_ms, end_ms = _date_range_ms(days)

        raw_orders = fetch_orders(client, start_ms, end_ms)

        all_line_items = []
        for order in raw_orders:
            order_id = order.get("id")
            if not order_id:
                continue
            line_items = fetch_line_items(client, order_id)
            all_line_items.extend(line_items)

        daily_aggregates = aggregate_line_items(all_line_items)
        sales_rows = list(daily_aggregates.values())
        if sales_rows:
            upsert_daily_sales(sales_rows)
        records_fetched += len(all_line_items)

        raw_stocks = fetch_item_stocks(client)
        clean_stocks = [clean_stock(r) for r in raw_stocks]
        clean_stocks = [s for s in clean_stocks if s.get("item_id")]
        if clean_stocks:
            insert_stock_snapshots(clean_stocks)
        records_fetched += len(clean_stocks)

        log_sync(mode, records_fetched, "success")

        return {
            "status": "success",
            "mode": mode,
            "categories_synced": len(clean_cats),
            "items_synced": len(clean_items),
            "orders_processed": len(raw_orders),
            "line_items_processed": len(all_line_items),
            "daily_sales_rows": len(sales_rows),
            "stock_snapshots": len(clean_stocks),
            "records_fetched": records_fetched,
        }

    except Exception as exc:
        error_msg = str(exc)[:500]
        log_sync(mode, records_fetched, "failed", error_msg)
        raise
