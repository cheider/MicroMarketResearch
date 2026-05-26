"""
Naive forecasts and reorder suggestions for micro-market inventory planning.
"""

import math
import pandas as pd

from app.database import get_connection
from app.analysis.periods import resolve_period


def _latest_stock() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(
            """
            SELECT ss.item_id, ss.quantity
            FROM stock_snapshots ss
            WHERE ss.id IN (SELECT MAX(id) FROM stock_snapshots GROUP BY item_id)
            """,
            conn,
        )


def _velocity_7d() -> pd.DataFrame:
    bounds = resolve_period("7d")
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT ds.item_id,
                   SUM(ds.units_sold) AS units_7d
            FROM daily_sales ds
            WHERE ds.sale_date BETWEEN :start AND :end
            GROUP BY ds.item_id
            """,
            conn,
            params={"start": bounds["start"], "end": bounds["end"]},
        )
    if df.empty:
        return df
    df["avg_daily_units"] = (df["units_7d"] / 7).round(2)
    return df


def forecast_item_units(item_id: str, horizon_days: int = 14) -> dict | None:
    vel = _velocity_7d()
    row = vel[vel["item_id"] == item_id]
    if row.empty:
        return None
    avg = float(row.iloc[0]["avg_daily_units"])
    projected = round(avg * horizon_days, 1)
    return {
        "item_id": item_id,
        "avg_daily_units": avg,
        "horizon_days": horizon_days,
        "projected_units": projected,
    }


def reorder_suggestions(target_days_cover: int = 7, min_avg_daily: float = 0.1) -> list:
    vel = _velocity_7d()
    stock = _latest_stock()
    if vel.empty:
        return []

    with get_connection() as conn:
        items_df = pd.read_sql(
            "SELECT item_id, name, price_cents FROM items WHERE is_active = 1",
            conn,
        )

    merged = items_df.merge(vel, on="item_id", how="left").merge(
        stock, on="item_id", how="left"
    )
    merged["avg_daily_units"] = merged["avg_daily_units"].fillna(0)
    merged["quantity"] = merged["quantity"].fillna(0).astype(int)

    rows = []
    for _, r in merged.iterrows():
        avg = float(r["avg_daily_units"])
        if avg < min_avg_daily:
            continue
        on_hand = int(r["quantity"])
        need = math.ceil(avg * target_days_cover)
        suggested = max(0, need - on_hand)
        days_left = round(on_hand / avg, 1) if avg > 0 else None
        rows.append({
            "item_id": r["item_id"],
            "name": r["name"],
            "avg_daily_units": avg,
            "on_hand": on_hand,
            "days_until_stockout": days_left,
            "suggested_reorder_qty": suggested,
            "projected_14d_units": round(avg * 14, 1),
        })

    return sorted(rows, key=lambda x: (x["days_until_stockout"] or 999))


def stockout_risk_items(max_days: float = 3.0) -> list:
    suggestions = reorder_suggestions()
    return [r for r in suggestions if r["days_until_stockout"] is not None and r["days_until_stockout"] < max_days]


def get_forecast_summary(horizon_days: int = 14) -> dict:
    vel = _velocity_7d()
    if vel.empty:
        return {"total_projected_units": 0, "total_projected_revenue_cents": 0, "item_count": 0}

    with get_connection() as conn:
        prices = pd.read_sql(
            "SELECT item_id, price_cents FROM items WHERE is_active = 1",
            conn,
        )
    merged = vel.merge(prices, on="item_id")
    merged["projected_units"] = merged["avg_daily_units"] * horizon_days
    merged["projected_revenue_cents"] = (
        merged["projected_units"] * merged["price_cents"]
    ).astype(int)

    return {
        "horizon_days": horizon_days,
        "total_projected_units": round(merged["projected_units"].sum(), 1),
        "total_projected_revenue_cents": int(merged["projected_revenue_cents"].sum()),
        "item_count": len(merged),
    }
