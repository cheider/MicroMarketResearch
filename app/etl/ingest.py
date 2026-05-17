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

import logging
from datetime import datetime, timedelta, timezone

from app.clover.endpoints import (
    fetch_categories,
    fetch_items,
    fetch_orders,
    fetch_line_items,
    fetch_item_stocks,
)
from app.etl.transform import (
    clean_category,
    clean_item,
    clean_stock,
    aggregate_line_items,
)
from app.etl.load import (
    upsert_categories,
    upsert_items,
    upsert_daily_sales,
    insert_stock_snapshots,
    log_sync,
    get_last_successful_sync_ts,
)

logger = logging.getLogger(__name__)


def _date_range_ms(days_back: int) -> tuple[int, int]:
    """Returns (start_ms, end_ms) for a UTC window ending now."""
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=days_back)
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def _ts_to_ms(iso_ts: str) -> int:
    """Converts an ISO-8601 timestamp string to milliseconds since epoch."""
    dt = datetime.fromisoformat(iso_ts)
    return int(dt.timestamp() * 1000)


def run_full_ingest(client, days: int = 30, on_progress=None) -> dict:
    """
    Pulls all items, orders, and stock for the past `days` days.
    Returns a summary dict with counts and status.
    """
    return _run_ingest(client, mode="full", days=days, on_progress=on_progress)


def run_incremental_ingest(client, days: int = 30, on_progress=None) -> dict:
    """
    Pulls data since the last successful sync.
    Falls back to a full ingest if no prior sync exists.
    """
    last_sync = get_last_successful_sync_ts()
    if not last_sync:
        return run_full_ingest(client, days=days, on_progress=on_progress)
    return _run_ingest(
        client, mode="incremental", days=days,
        since_ts=last_sync, on_progress=on_progress,
    )


def _notify(on_progress, stage_id: str, status: str, count=None):
    """Call on_progress if provided; silently skip if None."""
    if on_progress is not None:
        on_progress(stage_id, status, count)


def _run_ingest(
    client, mode: str, days: int,
    since_ts: str = None, on_progress=None,
) -> dict:
    records_fetched = 0
    logger.info("Ingest started  mode=%s  days=%d", mode, days)
    _current_stage = None
    try:
        _current_stage = "categories"
        _notify(on_progress, "categories", "running")
        raw_categories = fetch_categories(client)
        clean_cats = [clean_category(r) for r in raw_categories]
        clean_cats = [c for c in clean_cats if c.get("category_id")]
        upsert_categories(clean_cats)
        records_fetched += len(clean_cats)
        logger.info("Categories fetched=%d", len(clean_cats))
        _notify(on_progress, "categories", "done", len(clean_cats))

        _current_stage = "items"
        _notify(on_progress, "items", "running")
        raw_items = fetch_items(client)
        clean_items = [clean_item(r) for r in raw_items]
        clean_items = [i for i in clean_items if i.get("item_id")]
        upsert_items(clean_items)
        records_fetched += len(clean_items)
        logger.info("Items fetched=%d", len(clean_items))
        _notify(on_progress, "items", "done", len(clean_items))

        if since_ts:
            start_ms = _ts_to_ms(since_ts)
            end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        else:
            start_ms, end_ms = _date_range_ms(days)

        _current_stage = "orders"
        _notify(on_progress, "orders", "running")
        logger.info(
            "Fetching orders  start_ms=%d  end_ms=%d", start_ms, end_ms
        )
        raw_orders = fetch_orders(client, start_ms, end_ms)
        logger.info("Orders fetched=%d", len(raw_orders))
        _notify(on_progress, "orders", "done", len(raw_orders))

        _current_stage = "line_items"
        _notify(on_progress, "line_items", "running")
        all_line_items = []
        for order in raw_orders:
            order_id = order.get("id")
            if not order_id:
                continue
            line_items = fetch_line_items(client, order_id)
            all_line_items.extend(line_items)
        logger.info(
            "Line items processed=%d", len(all_line_items)
        )
        _notify(on_progress, "line_items", "done", len(all_line_items))

        _current_stage = "daily_sales"
        _notify(on_progress, "daily_sales", "running")
        daily_aggregates = aggregate_line_items(all_line_items)
        sales_rows = list(daily_aggregates.values())
        if sales_rows:
            upsert_daily_sales(sales_rows)
        records_fetched += len(all_line_items)
        logger.info("Daily sales rows=%d", len(sales_rows))
        _notify(on_progress, "daily_sales", "done", len(sales_rows))

        _current_stage = "stock"
        _notify(on_progress, "stock", "running")
        raw_stocks = fetch_item_stocks(client)
        clean_stocks = [clean_stock(r) for r in raw_stocks]
        clean_stocks = [s for s in clean_stocks if s.get("item_id")]
        if clean_stocks:
            insert_stock_snapshots(clean_stocks)
        records_fetched += len(clean_stocks)
        logger.info("Stock snapshots inserted=%d", len(clean_stocks))
        _notify(on_progress, "stock", "done", len(clean_stocks))

        _current_stage = "log"
        _notify(on_progress, "log", "running")
        log_sync(mode, records_fetched, "success")
        logger.info(
            "Ingest complete  mode=%s  records_fetched=%d",
            mode,
            records_fetched,
        )
        _notify(on_progress, "log", "done", records_fetched)

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
        logger.error(
            "Ingest failed  stage=%s  mode=%s  error=%s",
            _current_stage, mode, error_msg, exc_info=True,
        )
        if _current_stage:
            _notify(on_progress, _current_stage, "error")
        log_sync(mode, records_fetched, "failed", error_msg)
        raise
