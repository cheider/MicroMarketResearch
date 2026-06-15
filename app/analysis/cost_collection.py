"""
Missing item cost export for manual collection and Clover entry.

Clover stores per-item cost as ``defaultCost`` (synced to ``items.cost_cents``).
This module lists active items with no cost and ranks them by recent sales.
"""

from __future__ import annotations

import pandas as pd

from app.database import get_connection
from app.analysis.periods import resolve_period


MISSING_COST_CSV_COLUMNS = [
    "item_id",
    "item_name",
    "clover_category",
    "product_type",
    "price_dollars",
    "cost_dollars_to_enter",
    "units_sold_90d",
    "revenue_dollars_90d",
    "track_inventory",
    "notes",
]


def get_missing_cost_items(
    sales_period: str = "90d",
    include_zero_price: bool = True,
    limit: int | None = None,
) -> list[dict]:
    """
    Active catalog items missing ``cost_cents``, sorted by units sold in period.

    Each row includes display fields plus raw cents for templates.
    """
    bounds = resolve_period(sales_period)

    price_clause = ""
    if not include_zero_price:
        price_clause = "AND i.price_cents > 0"

    limit_clause = ""
    params: dict = {"start": bounds["start"], "end": bounds["end"]}
    if limit is not None:
        limit_clause = "LIMIT :limit"
        params["limit"] = int(limit)

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                i.item_id,
                i.name AS item_name,
                COALESCE(c.name, '') AS clover_category,
                COALESCE(pc.name, ps.name, 'Uncategorized') AS product_type,
                i.price_cents,
                COALESCE(i.track_inventory, 1) AS track_inventory,
                COALESCE(SUM(ds.units_sold), 0) AS units_sold_90d,
                COALESCE(SUM(ds.gross_revenue_cents), 0) AS revenue_cents_90d
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.category_id
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            LEFT JOIN product_categories ps
              ON i.suggested_product_category_id = ps.product_category_id
            LEFT JOIN daily_sales ds
              ON i.item_id = ds.item_id
             AND ds.sale_date BETWEEN :start AND :end
            WHERE i.is_active = 1
              AND i.cost_cents IS NULL
              {price_clause}
            GROUP BY i.item_id, i.name, c.name, pc.name, ps.name,
                     i.price_cents, i.track_inventory
            ORDER BY units_sold_90d DESC, revenue_cents_90d DESC, i.name
            {limit_clause}
            """,
            conn,
            params=params,
        )

    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "item_id": r["item_id"],
            "item_name": r["item_name"],
            "clover_category": r["clover_category"],
            "product_type": r["product_type"],
            "price_cents": int(r["price_cents"] or 0),
            "price_dollars": round(int(r["price_cents"] or 0) / 100, 2),
            "units_sold_90d": int(r["units_sold_90d"]),
            "revenue_cents_90d": int(r["revenue_cents_90d"]),
            "revenue_dollars_90d": round(int(r["revenue_cents_90d"]) / 100, 2),
            "track_inventory": bool(int(r["track_inventory"])),
        })
    return rows


def missing_cost_dataframe(
    sales_period: str = "90d",
    include_zero_price: bool = True,
) -> pd.DataFrame:
    """CSV-ready DataFrame with blank columns for manual cost entry."""
    rows = get_missing_cost_items(
        sales_period=sales_period,
        include_zero_price=include_zero_price,
    )
    if not rows:
        return pd.DataFrame(columns=MISSING_COST_CSV_COLUMNS)

    df = pd.DataFrame(rows)
    df["price_dollars"] = df["price_cents"] / 100
    df["revenue_dollars_90d"] = df["revenue_cents_90d"] / 100
    df["cost_dollars_to_enter"] = ""
    df["track_inventory"] = df["track_inventory"].map({True: "yes", False: "no"})
    df["notes"] = ""

    return df[MISSING_COST_CSV_COLUMNS]
