"""
Profit margin analysis.

Computes per-item margin from the items table and classifies each item
into one of three categories: negative margin, low margin, or acceptable margin.
Items without a recorded cost are reported separately.
"""

import pandas as pd
from app.database import get_connection


def get_margin_report(threshold: float = 0.10) -> dict:
    """
    Returns a dict with four DataFrames:
        negative:  items with margin < 0 (selling below cost)
        low:       items with 0 <= margin < threshold
        acceptable: items with margin >= threshold
        no_cost:   items where cost_cents is NULL (margin cannot be computed)
    """
    with get_connection() as conn:
        df = pd.read_sql(
            "SELECT item_id, name, price_cents, cost_cents FROM items WHERE is_active = 1",
            conn,
        )

    if df.empty:
        empty = pd.DataFrame(columns=["item_id", "name", "price_cents", "cost_cents", "margin"])
        return {
            "negative": empty,
            "low": empty,
            "acceptable": empty,
            "no_cost": df,
            "threshold": threshold,
        }

    no_cost = df[df["cost_cents"].isna()].copy()
    has_cost = df[df["cost_cents"].notna()].copy()

    has_cost["margin"] = (
        (has_cost["price_cents"] - has_cost["cost_cents"]) / has_cost["price_cents"]
    ).round(4)

    has_cost["price_dollars"] = has_cost["price_cents"] / 100
    has_cost["cost_dollars"] = has_cost["cost_cents"] / 100
    has_cost["margin_pct"] = (has_cost["margin"] * 100).round(2)

    negative = has_cost[has_cost["margin"] < 0].sort_values("margin")
    low = has_cost[(has_cost["margin"] >= 0) & (has_cost["margin"] < threshold)].sort_values("margin")
    acceptable = has_cost[has_cost["margin"] >= threshold].sort_values("margin", ascending=False)

    return {
        "negative": negative,
        "low": low,
        "acceptable": acceptable,
        "no_cost": no_cost,
        "threshold": threshold,
        "total_items": len(df),
        "items_with_cost": len(has_cost),
    }


def get_item_margin(item_id: str) -> dict | None:
    """Returns margin data for a single item, or None if not found."""
    with get_connection() as conn:
        df = pd.read_sql(
            "SELECT item_id, name, price_cents, cost_cents FROM items WHERE item_id = ?",
            conn,
            params=(item_id,),
        )

    if df.empty:
        return None

    row = df.iloc[0]
    price = row["price_cents"]
    cost = row["cost_cents"]

    margin = None
    if pd.notna(cost) and price > 0:
        margin = round((price - cost) / price, 4)

    return {
        "item_id": row["item_id"],
        "name": row["name"],
        "price_dollars": price / 100,
        "cost_dollars": cost / 100 if pd.notna(cost) else None,
        "margin": margin,
        "margin_pct": round(margin * 100, 2) if margin is not None else None,
    }
