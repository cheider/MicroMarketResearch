"""
Category analysis summaries for the dedicated analysis page.

All sales and assignment rollups use **app product types**
(``items.product_category_id`` / suggested buckets from Inventory Tools),
not raw Clover import tags (``items.category_id`` / ``categories``).
"""

from __future__ import annotations

import pandas as pd

from app.database import get_connection
from app.analysis.dashboard_analytics import get_sales_by_category
from app.analysis.periods import resolve_period
from app.analysis.category_resolution import (
    category_bucket_exprs,
    category_filter_clause,
    category_joins,
)
from app.inventory_tools.categorization_service import get_inventory_tools_stats

# Category Analysis always includes rule-based suggestions so the page
# matches the category board (ghost suggestions + confirmed assignments).
USE_SUGGESTED_PRODUCT_TYPES = True

_POPULARITY_LINE_COLORS = (
    "rgba(79, 142, 247, 0.9)",
    "rgba(25, 135, 84, 0.9)",
    "rgba(253, 126, 20, 0.9)",
    "rgba(111, 66, 193, 0.9)",
    "rgba(220, 53, 69, 0.9)",
)


def get_assignment_by_product_type() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                COALESCE(pc.name, 'Uncategorized') AS name,
                COALESCE(i.product_category_id, 'uncategorized') AS slug,
                COUNT(*) AS item_count,
                SUM(CASE WHEN i.product_category_source = 'manual' THEN 1 ELSE 0 END)
                    AS manual_count,
                SUM(CASE WHEN i.product_category_source = 'suggested' THEN 1 ELSE 0 END)
                    AS suggested_count,
                SUM(CASE WHEN i.product_category_source = 'clover' THEN 1 ELSE 0 END)
                    AS clover_count
            FROM items i
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            WHERE i.is_active = 1
            GROUP BY i.product_category_id, pc.name
            ORDER BY item_count DESC, name
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _top_item_ids(
    start: str,
    end: str,
    category_id: str | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Top items by units sold in period, optionally filtered to one product type."""
    cat_join = category_joins(USE_SUGGESTED_PRODUCT_TYPES)
    cat_where = ""
    params: dict = {"start": start, "end": end, "top_n": top_n}
    if category_id:
        filter_sql, filter_params = category_filter_clause(
            category_id, USE_SUGGESTED_PRODUCT_TYPES
        )
        cat_where = filter_sql
        params.update(filter_params)

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                i.item_id,
                i.name,
                SUM(ds.units_sold) AS units_sold
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            {cat_join}
            WHERE ds.sale_date BETWEEN :start AND :end
            {cat_where}
            GROUP BY i.item_id, i.name
            ORDER BY units_sold DESC
            LIMIT :top_n
            """,
            conn,
            params=params,
        )

    if df.empty:
        return []
    df["units_sold"] = df["units_sold"].fillna(0).astype(int)
    return df.to_dict(orient="records")


def _daily_units_for_items(
    start: str,
    end: str,
    item_ids: list[str],
) -> tuple[list[str], dict[str, list[int]]]:
    if not item_ids:
        return [], {}

    placeholders = ", ".join(f":id{i}" for i in range(len(item_ids)))
    params: dict = {"start": start, "end": end}
    params.update({f"id{i}": item_id for i, item_id in enumerate(item_ids)})

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT ds.sale_date, ds.item_id, SUM(ds.units_sold) AS units_sold
            FROM daily_sales ds
            WHERE ds.sale_date BETWEEN :start AND :end
              AND ds.item_id IN ({placeholders})
            GROUP BY ds.sale_date, ds.item_id
            ORDER BY ds.sale_date
            """,
            conn,
            params=params,
        )

    if df.empty:
        return [], {item_id: [] for item_id in item_ids}

    labels = sorted(df["sale_date"].unique().tolist())
    by_item: dict[str, list[int]] = {item_id: [] for item_id in item_ids}
    pivot = df.pivot_table(
        index="sale_date", columns="item_id", values="units_sold", aggfunc="sum", fill_value=0
    )
    for label in labels:
        for item_id in item_ids:
            val = int(pivot.loc[label, item_id]) if item_id in pivot.columns else 0
            by_item[item_id].append(val)

    return labels, by_item


def _build_popularity_chart(
    start: str,
    end: str,
    category_id: str | None = None,
    top_n: int = 5,
) -> dict:
    top_items = _top_item_ids(start, end, category_id=category_id, top_n=top_n)
    if not top_items:
        return {"labels": [], "series": []}

    item_ids = [row["item_id"] for row in top_items]
    labels, units_by_item = _daily_units_for_items(start, end, item_ids)

    series = []
    for i, row in enumerate(top_items):
        item_id = row["item_id"]
        series.append({
            "item_id": item_id,
            "name": row["name"],
            "color": _POPULARITY_LINE_COLORS[i % len(_POPULARITY_LINE_COLORS)],
            "values": units_by_item.get(item_id, [0] * len(labels)),
            "total_units": int(row["units_sold"]),
        })

    return {"labels": labels, "series": series}


def get_overall_product_popularity(period: str = "90d", top_n: int = 5) -> dict:
    """Daily units sold for the top-N products store-wide."""
    info = resolve_period(period)
    return _build_popularity_chart(info["start"], info["end"], category_id=None, top_n=top_n)


def get_category_product_popularity(period: str = "90d", top_n: int = 5) -> list[dict]:
    """
    Daily units sold for the top-N products within each product type that had sales.
    """
    info = resolve_period(period)
    by_product = get_sales_by_category(
        period=period, use_suggested=USE_SUGGESTED_PRODUCT_TYPES
    )

    blocks: list[dict] = []
    for cat in by_product:
        chart = _build_popularity_chart(
            info["start"],
            info["end"],
            category_id=cat["category_id"],
            top_n=top_n,
        )
        if not chart["series"]:
            continue
        blocks.append({
            "category_id": cat["category_id"],
            "name": cat["name"],
            "labels": chart["labels"],
            "series": chart["series"],
        })
    return blocks


def get_category_analysis_report(
    period: str = "90d",
) -> dict:
    period_info = resolve_period(period)
    stats = get_inventory_tools_stats()
    by_product = get_sales_by_category(
        period=period, use_suggested=USE_SUGGESTED_PRODUCT_TYPES
    )
    assignments = get_assignment_by_product_type()

    chart_labels = [r["name"] for r in by_product]
    chart_revenue = [int(r["revenue_cents"]) for r in by_product]
    chart_units = [int(r["units_sold"]) for r in by_product]

    return {
        "period": period,
        "period_info": period_info,
        "stats": stats,
        "by_product": by_product,
        "assignments": assignments,
        "chart_labels": chart_labels,
        "chart_revenue": chart_revenue,
        "chart_units": chart_units,
        "popularity_overall": get_overall_product_popularity(period=period),
        "popularity_by_category": get_category_product_popularity(period=period),
    }
