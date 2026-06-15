"""
Find catalog items with no retail price and export them to Excel.

Missing price means price_cents is NULL or <= 0 (Clover items without a price
sync as 0 in the local database).

Usage:
    python scripts/report_missing_prices.py
    python scripts/report_missing_prices.py --output reports/missing_prices.xlsx
    python scripts/report_missing_prices.py --live
    python scripts/report_missing_prices.py --include-inactive
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.database import get_connection, init_db
from app.clover.client import CloverClient, CloverAPIError
from app.clover.endpoints import fetch_items
from app.etl.transform import clean_item

EXPORT_COLUMNS = [
    "item_id",
    "name",
    "price_cents",
    "price_dollars",
    "cost_cents",
    "cost_dollars",
    "category_id",
    "category_name",
    "is_active",
    "last_synced",
    "issue",
]

SUMMARY_COLUMNS = ["metric", "value"]


def _price_issue(price_cents) -> str | None:
    if price_cents is None or (isinstance(price_cents, float) and pd.isna(price_cents)):
        return "null_price"
    if int(price_cents) <= 0:
        return "zero_price"
    return None


def _format_export_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=EXPORT_COLUMNS)

    out = df.copy()
    out["price_cents"] = pd.to_numeric(out["price_cents"], errors="coerce")
    out["cost_cents"] = pd.to_numeric(out.get("cost_cents"), errors="coerce")
    out["issue"] = out["price_cents"].apply(_price_issue)
    out = out[out["issue"].notna()].copy()

    out["price_dollars"] = out["price_cents"].apply(
        lambda v: None if pd.isna(v) else round(float(v) / 100, 2)
    )
    out["cost_dollars"] = out["cost_cents"].apply(
        lambda v: None if pd.isna(v) else round(float(v) / 100, 2)
    )
    out["is_active"] = out["is_active"].map({1: "yes", 0: "no", True: "yes", False: "no"})

    for col in EXPORT_COLUMNS:
        if col not in out.columns:
            out[col] = None

    return out[EXPORT_COLUMNS].sort_values(["category_name", "name"], na_position="last")


def fetch_missing_prices_from_db(include_inactive: bool = False) -> pd.DataFrame:
    active_clause = "" if include_inactive else "AND i.is_active = 1"
    query = f"""
        SELECT
            i.item_id,
            i.name,
            i.price_cents,
            i.cost_cents,
            i.category_id,
            c.name AS category_name,
            i.is_active,
            i.last_synced
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.category_id
        WHERE (i.price_cents IS NULL OR i.price_cents <= 0)
        {active_clause}
        ORDER BY i.name
    """
    with get_connection() as conn:
        return pd.read_sql(query, conn)


def fetch_missing_prices_live(include_inactive: bool = False) -> pd.DataFrame:
    cfg = Config()
    client = CloverClient(cfg)
    synced = datetime.now(tz=timezone.utc).isoformat()

    rows = []
    for raw in fetch_items(client):
        cleaned = clean_item(raw)
        if not include_inactive and not cleaned["is_active"]:
            continue
        rows.append(
            {
                "item_id": cleaned["item_id"],
                "name": cleaned["name"],
                "price_cents": cleaned["price_cents"],
                "cost_cents": cleaned["cost_cents"],
                "category_id": cleaned["category_id"],
                "category_name": None,
                "is_active": cleaned["is_active"],
                "last_synced": synced,
            }
        )

    return pd.DataFrame(rows)


def build_summary(
    missing_df: pd.DataFrame,
    total_items: int,
    source: str,
    generated_at: str,
) -> pd.DataFrame:
    rows = [
        ("generated_at_utc", generated_at),
        ("source", source),
        ("total_items_checked", total_items),
        ("missing_price_count", len(missing_df)),
        ("null_price_count", int((missing_df["issue"] == "null_price").sum()) if not missing_df.empty else 0),
        ("zero_price_count", int((missing_df["issue"] == "zero_price").sum()) if not missing_df.empty else 0),
        ("active_missing_count", int((missing_df["is_active"] == "yes").sum()) if not missing_df.empty else 0),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def default_output_path() -> str:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return os.path.join("reports", f"missing_prices_{stamp}.xlsx")


def write_excel(missing_df: pd.DataFrame, summary_df: pd.DataFrame, output_path: str) -> None:
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        missing_df.to_excel(writer, sheet_name="Missing Prices", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)


def count_total_items_from_db(include_inactive: bool) -> int:
    active_clause = "" if include_inactive else "WHERE is_active = 1"
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS cnt FROM items {active_clause}").fetchone()
    return int(row["cnt"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export items with missing prices (NULL or zero) to Excel."
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output .xlsx path (default: reports/missing_prices_<timestamp>.xlsx)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch the current Clover catalog instead of reading the local database",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include hidden/inactive items",
    )
    args = parser.parse_args()

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    output_path = args.output or default_output_path()

    if args.live:
        cfg = Config()
        if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
            print("FAIL: --live requires CLOVER_API_TOKEN and CLOVER_MERCHANT_ID in .env")
            sys.exit(1)
        try:
            raw_df = fetch_missing_prices_live(include_inactive=args.include_inactive)
        except CloverAPIError as exc:
            print(f"FAIL: Clover API error: {exc}")
            sys.exit(1)
        missing_df = _format_export_df(raw_df)
        total_items = len(raw_df)
        source = "clover_live"
    else:
        cfg = Config()
        if not os.path.exists(cfg.DB_PATH):
            print(f"FAIL: Database not found at {cfg.DB_PATH!r}")
            print("Run a sync first (e.g. python scripts/seed_sandbox.py) or use --live.")
            sys.exit(1)
        init_db(cfg.DB_PATH)
        raw_df = fetch_missing_prices_from_db(include_inactive=args.include_inactive)
        missing_df = _format_export_df(raw_df)
        total_items = count_total_items_from_db(args.include_inactive)
        source = f"database:{cfg.DB_PATH}"

    summary_df = build_summary(missing_df, total_items, source, generated_at)

    try:
        write_excel(missing_df, summary_df, output_path)
    except ImportError:
        print("FAIL: openpyxl is required. Install with: pip install openpyxl")
        sys.exit(1)

    print(f"Wrote {len(missing_df)} missing-price item(s) to {output_path}")
    print(f"Checked {total_items} item(s) from {source}")


if __name__ == "__main__":
    main()
