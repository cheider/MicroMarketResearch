"""
Item profile aggregation: taxonomy, supplier/location inference, lifetime sales.
"""

from __future__ import annotations

import re

from app.analysis.margins import get_item_margin
from app.database import get_connection
from app.taxonomy import CAFE_PRODUCT_SLUGS, clover_category_kind, normalize_name

_SUPPLIER_PATTERNS: list[tuple[str, str]] = [
    (r"cheetos|maruchan|snack club|snak club|rice krispie", "Snak Club"),
    (r"us foods|usfood", "US Foods"),
    (r"harried", "Harried & Hungry"),
]


def infer_supplier(clover_tag_name: str | None, item_name: str) -> str:
    if clover_tag_name and clover_category_kind(clover_tag_name) == "supplier":
        return clover_tag_name.strip()

    lower = (item_name or "").lower()
    for pattern, label in _SUPPLIER_PATTERNS:
        if re.search(pattern, lower):
            return label
    return "Unassigned"


def infer_primary_location(
    clover_tag_name: str | None,
    clover_tag_kind: str | None,
    product_category_id: str | None,
) -> dict:
    if clover_tag_kind == "location" and clover_tag_name:
        return {
            "name": clover_tag_name.strip(),
            "inferred": False,
            "note": None,
        }

    slug = (product_category_id or "").strip()
    if slug in CAFE_PRODUCT_SLUGS:
        return {
            "name": "Lily Pad Cafe",
            "inferred": True,
            "note": "Inferred from product type (no per-register sales in database).",
        }
    if slug == "school_supplies":
        return {
            "name": "Bookstore",
            "inferred": True,
            "note": "Inferred from product type (no per-register sales in database).",
        }
    return {
        "name": "Unknown / multiple",
        "inferred": True,
        "note": "Inferred — add a Clover location tag or wait for register-level ETL.",
    }


def get_item_profile(item_id: str) -> dict | None:
    margin = get_item_margin(item_id)
    if not margin:
        return None

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                i.item_id,
                i.name,
                i.price_cents,
                i.product_category_id,
                i.suggested_product_category_id,
                i.product_category_source,
                i.category_id,
                c.name AS clover_category_name,
                c.kind AS clover_category_kind,
                pc.name AS product_category_name,
                ps.name AS suggested_product_category_name,
                COALESCE(SUM(ds.units_sold), 0) AS lifetime_units,
                COALESCE(SUM(ds.gross_revenue_cents), 0) AS lifetime_revenue_cents,
                MIN(ds.sale_date) AS first_sale_date,
                MAX(ds.sale_date) AS last_sale_date
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.category_id
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            LEFT JOIN product_categories ps
              ON i.suggested_product_category_id = ps.product_category_id
            LEFT JOIN daily_sales ds ON i.item_id = ds.item_id
            WHERE i.item_id = ?
            GROUP BY i.item_id, i.name, i.price_cents, i.product_category_id,
                     i.suggested_product_category_id, i.product_category_source,
                     i.category_id, c.name, c.kind, pc.name, ps.name
            """,
            (item_id,),
        ).fetchone()

        stock_row = conn.execute(
            """
            SELECT quantity
            FROM stock_snapshots
            WHERE item_id = ?
            ORDER BY snapshot_ts DESC
            LIMIT 1
            """,
            (item_id,),
        ).fetchone()

    effective_slug = row["product_category_id"] or row["suggested_product_category_id"]
    effective_name = (
        row["product_category_name"]
        or row["suggested_product_category_name"]
        or "Uncategorized"
    )
    has_suggestion_only = (
        not row["product_category_id"] and row["suggested_product_category_id"]
    )

    location = infer_primary_location(
        row["clover_category_name"],
        row["clover_category_kind"],
        effective_slug,
    )

    profile = {
        **margin,
        "product_category_id": row["product_category_id"],
        "product_category_name": effective_name,
        "product_category_source": row["product_category_source"],
        "has_suggestion_only": has_suggestion_only,
        "suggested_product_category_id": row["suggested_product_category_id"],
        "suggested_product_category_name": row["suggested_product_category_name"],
        "clover_category": row["clover_category_name"],
        "clover_category_kind": row["clover_category_kind"],
        "supplier": infer_supplier(row["clover_category_name"], row["name"]),
        "primary_location": location["name"],
        "location_inferred": location["inferred"],
        "location_note": location["note"],
        "lifetime_units_sold": int(row["lifetime_units"] or 0),
        "lifetime_revenue_cents": int(row["lifetime_revenue_cents"] or 0),
        "lifetime_revenue_dollars": round(
            int(row["lifetime_revenue_cents"] or 0) / 100, 2
        ),
        "first_sale_date": row["first_sale_date"],
        "last_sale_date": row["last_sale_date"],
        "on_hand_qty": int(stock_row["quantity"]) if stock_row else None,
    }
    return profile
