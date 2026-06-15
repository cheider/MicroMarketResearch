"""
Category analysis summaries for the dedicated analysis page.

All sales and assignment rollups use **app product types**
(``items.product_category_id`` / suggested buckets from Inventory Tools),
not raw Clover import tags (``items.category_id`` / ``categories``).
"""

from __future__ import annotations

from app.database import get_connection
from app.analysis.dashboard_analytics import get_sales_by_category
from app.analysis.periods import resolve_period
from app.inventory_tools.categorization_service import get_inventory_tools_stats

# Category Analysis always includes rule-based suggestions so the page
# matches the category board (ghost suggestions + confirmed assignments).
USE_SUGGESTED_PRODUCT_TYPES = True


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
    }
