"""
Inventory shrinkage analysis.

Compares expected stock (oldest snapshot minus units sold) against
actual stock (newest snapshot) to surface items where inventory
disappeared without corresponding sales records.

Positive shrinkage_units means stock is lower than sales records account for,
which indicates theft, damage, data entry errors, or unrecorded transactions.
"""

import pandas as pd
from app.database import get_connection


def get_shrinkage_report(days: int = 30) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per item that has both stock snapshots
    and sales data within the lookback window.

    Columns:
        item_id, name, price_cents, cost_cents,
        oldest_snapshot_ts, newest_snapshot_ts,
        opening_stock, closing_stock,
        units_sold, expected_stock,
        shrinkage_units, shrinkage_value_cents
    """
    with get_connection() as conn:
        items_df = pd.read_sql(
            "SELECT item_id, name, price_cents, cost_cents FROM items WHERE is_active = 1",
            conn,
        )

        snapshots_df = pd.read_sql(
            f"""
            SELECT item_id, snapshot_ts, quantity
            FROM stock_snapshots
            WHERE snapshot_ts >= datetime('now', '-{days} days')
            ORDER BY snapshot_ts
            """,
            conn,
        )

        sales_df = pd.read_sql(
            f"""
            SELECT item_id, SUM(units_sold) as units_sold
            FROM daily_sales
            WHERE sale_date >= date('now', '-{days} days')
            GROUP BY item_id
            """,
            conn,
        )

    if snapshots_df.empty:
        return pd.DataFrame(columns=[
            "item_id", "name", "price_cents", "cost_cents",
            "opening_stock", "closing_stock", "units_sold",
            "expected_stock", "shrinkage_units", "shrinkage_value_cents",
        ])

    oldest = snapshots_df.groupby("item_id").first().reset_index()
    oldest = oldest.rename(columns={"quantity": "opening_stock", "snapshot_ts": "oldest_snapshot_ts"})

    newest = snapshots_df.groupby("item_id").last().reset_index()
    newest = newest.rename(columns={"quantity": "closing_stock", "snapshot_ts": "newest_snapshot_ts"})

    merged = oldest[["item_id", "opening_stock", "oldest_snapshot_ts"]].merge(
        newest[["item_id", "closing_stock", "newest_snapshot_ts"]],
        on="item_id",
        how="inner",
    )

    merged = merged.merge(sales_df, on="item_id", how="left")
    merged["units_sold"] = merged["units_sold"].fillna(0).astype(int)

    merged["expected_stock"] = merged["opening_stock"] - merged["units_sold"]
    merged["shrinkage_units"] = merged["expected_stock"] - merged["closing_stock"]

    merged = merged.merge(items_df, on="item_id", how="left")
    merged["shrinkage_value_cents"] = merged["shrinkage_units"] * merged["price_cents"]

    result = merged[[
        "item_id", "name", "price_cents", "cost_cents",
        "oldest_snapshot_ts", "newest_snapshot_ts",
        "opening_stock", "closing_stock", "units_sold",
        "expected_stock", "shrinkage_units", "shrinkage_value_cents",
    ]].sort_values("shrinkage_units", ascending=False)

    return result


def get_item_shrinkage(item_id: str, days: int = 30) -> dict | None:
    """Returns shrinkage data for a single item."""
    df = get_shrinkage_report(days=days)
    if df.empty:
        return None
    row = df[df["item_id"] == item_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()
