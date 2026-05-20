"""
Standalone script to initialize the SQLite database and verify the schema.
Run once before starting the application for the first time.

Usage:
    python scripts/init_db.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.database import init_db, column_audit

EXPECTED_TABLES = {
    "items": {"item_id", "name", "price_cents", "cost_cents", "is_active", "last_synced"},
    "daily_sales": {"id", "item_id", "sale_date", "units_sold", "gross_revenue_cents"},
    "stock_snapshots": {"id", "item_id", "snapshot_ts", "quantity"},
    "sync_log": {"id", "sync_ts", "sync_type", "records_fetched", "status", "error_detail"},
}

PII_COLUMN_NAMES = {
    "customer", "customer_id", "customer_name", "email",
    "employee", "employee_id", "card", "last4", "card_type",
    "tender", "card_brand", "card_token",
}


def main():
    cfg = Config()
    print(f"Initializing database at: {cfg.DB_PATH}")
    init_db(cfg.DB_PATH)

    print("Schema created. Running verification...")
    all_ok = True

    for table, expected_cols in EXPECTED_TABLES.items():
        actual_cols = set(column_audit(table))
        missing = expected_cols - actual_cols
        pii_found = PII_COLUMN_NAMES & actual_cols

        if missing:
            print(f"  FAIL: {table} is missing columns: {missing}")
            all_ok = False
        elif pii_found:
            print(f"  FAIL: {table} contains PII columns: {pii_found}")
            all_ok = False
        else:
            print(f"  OK:   {table} ({len(actual_cols)} columns, no PII detected)")

    if all_ok:
        print("Database initialization complete.")
    else:
        print("Verification failed. Review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
