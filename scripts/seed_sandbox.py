"""
Populates the local database from Clover sandbox data.

Use this after setting up a sandbox merchant with test items and orders.
Run once to verify the ETL pipeline end-to-end before switching to production.

Usage:
    python scripts/seed_sandbox.py
    python scripts/seed_sandbox.py --days 30
    python scripts/seed_sandbox.py --mode full
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.database import init_db, column_audit, get_connection
from app.clover.client import CloverClient, CloverAPIError
from app.etl.ingest import run_full_ingest, run_incremental_ingest

PII_COLUMN_NAMES = {
    "customer", "customer_id", "customer_name", "email",
    "employee", "employee_id", "card", "last4", "card_type",
    "tender", "card_brand", "card_token",
}

TABLES = ["items", "daily_sales", "stock_snapshots", "sync_log"]


def verify_no_pii():
    print("\nRunning post-seed PII audit...")
    clean = True
    for table in TABLES:
        cols = set(column_audit(table))
        found = PII_COLUMN_NAMES & cols
        if found:
            print(f"  FAIL: {table} contains PII columns: {found}")
            clean = False
        else:
            print(f"  OK:   {table}")
    return clean


def print_row_counts():
    print("\nRow counts:")
    with get_connection() as conn:
        for table in TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count}")


def print_margin_preview():
    print("\nSample margin data (first 5 items with cost):")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name, price_cents, cost_cents,
                   ROUND(CAST(price_cents - cost_cents AS REAL) / price_cents * 100, 1) as margin_pct
            FROM items
            WHERE cost_cents IS NOT NULL AND is_active = 1
            ORDER BY margin_pct ASC
            LIMIT 5
            """
        ).fetchall()
    if rows:
        for row in rows:
            print(f"  {row['name']}: ${row['price_cents']/100:.2f} / ${row['cost_cents']/100:.2f} = {row['margin_pct']}%")
    else:
        print("  No items with cost data found.")


def main():
    parser = argparse.ArgumentParser(description="Seed local DB from Clover sandbox.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full")
    args = parser.parse_args()

    print("Loading config from .env...")
    cfg = Config()
    print(f"  Merchant ID: {cfg.CLOVER_MERCHANT_ID}")
    print(f"  Base URL:    {cfg.CLOVER_BASE_URL}")
    print(f"  DB path:     {cfg.DB_PATH}")

    print("\nInitializing database schema...")
    init_db(cfg.DB_PATH)

    print("\nConnecting to Clover API...")
    client = CloverClient(cfg)

    try:
        test_response = client.get("items", params={"limit": 1})
        item_count = len(test_response.get("elements", []))
        print(f"  Connection OK. Items endpoint returned {item_count} result(s).")
    except CloverAPIError as exc:
        print(f"  Connection FAILED: {exc}")
        sys.exit(1)

    print(f"\nRunning {args.mode} ingest for {args.days} days...")
    try:
        if args.mode == "full":
            result = run_full_ingest(client, days=args.days)
        else:
            result = run_incremental_ingest(client, days=args.days)
        print(f"  Status: {result['status']}")
        print(f"  Items synced: {result['items_synced']}")
        print(f"  Orders processed: {result['orders_processed']}")
        print(f"  Line items processed: {result['line_items_processed']}")
        print(f"  Daily sales rows: {result['daily_sales_rows']}")
        print(f"  Stock snapshots: {result['stock_snapshots']}")
    except Exception as exc:
        print(f"  Ingest FAILED: {exc}")
        sys.exit(1)

    print_row_counts()
    print_margin_preview()
    pii_clean = verify_no_pii()

    if not pii_clean:
        print("\nPII audit failed. Review the database before using in production.")
        sys.exit(1)
    else:
        print("\nSeed complete. All checks passed.")


if __name__ == "__main__":
    main()
