"""
Sales velocity analysis.

Ranks items by unit volume and revenue contribution over a configurable
lookback window. Returns top and bottom seller lists.
"""

import pandas as pd
from app.database import get_connection


def get_velocity_report(days: int = 30, top_n: int = 20) -> dict:
    """
    Returns a dict with:
        top_sellers:    DataFrame of top_n items by units_sold
        bottom_sellers: DataFrame of bottom_n items by units_sold
        all_items:      Full ranked DataFrame
        total_revenue_cents: int
        period_days: int
    """
    with get_connection() as conn:
        sales_df = pd.read_sql(
            f"""
            SELECT ds.item_id,
                   SUM(ds.units_sold) as units_sold,
                   SUM(ds.gross_revenue_cents) as gross_revenue_cents
            FROM daily_sales ds
            WHERE ds.sale_date >= date('now', '-{days} days')
            GROUP BY ds.item_id
            """,
            conn,
        )
        items_df = pd.read_sql(
            "SELECT item_id, name, price_cents, cost_cents FROM items WHERE is_active = 1",
            conn,
        )

    if sales_df.empty:
        empty = pd.DataFrame(columns=[
            "item_id", "name", "units_sold", "gross_revenue_cents", "revenue_share_pct",
        ])
        return {
            "top_sellers": empty,
            "bottom_sellers": empty,
            "all_items": empty,
            "total_revenue_cents": 0,
            "period_days": days,
        }

    merged = sales_df.merge(items_df, on="item_id", how="left")
    merged["name"] = merged["name"].fillna("Unknown Item")

    total_revenue = int(merged["gross_revenue_cents"].sum())
    merged["revenue_share_pct"] = (
        (merged["gross_revenue_cents"] / total_revenue * 100).round(2)
        if total_revenue > 0
        else 0.0
    )
    merged["price_dollars"] = merged["price_cents"] / 100

    merged = merged.sort_values("units_sold", ascending=False).reset_index(drop=True)
    merged["rank"] = merged.index + 1

    top_sellers = merged.head(top_n)
    bottom_sellers = merged.tail(top_n).sort_values("units_sold")

    return {
        "top_sellers": top_sellers,
        "bottom_sellers": bottom_sellers,
        "all_items": merged,
        "total_revenue_cents": total_revenue,
        "period_days": days,
    }


def get_item_sales_series(item_id: str, days: int = 30) -> list:
    """
    Returns a list of {"date": str, "units_sold": int, "gross_revenue_cents": int}
    for Chart.js sparkline rendering on the item detail page.
    """
    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT sale_date as date, units_sold, gross_revenue_cents
            FROM daily_sales
            WHERE item_id = ? AND sale_date >= date('now', '-{days} days')
            ORDER BY sale_date
            """,
            conn,
            params=(item_id,),
        )
    return df.to_dict(orient="records")
