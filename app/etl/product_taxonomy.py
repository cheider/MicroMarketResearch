"""
Classify Clover categories and derive per-item product categories.
"""

from __future__ import annotations

from app.database import get_connection
from app.taxonomy import (
    PRODUCT_CATEGORIES,
    clover_category_kind,
    clover_product_name_to_slug,
)


def seed_product_categories() -> None:
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO product_categories
                (product_category_id, name, color_hex, sort_order)
            VALUES (:product_category_id, :name, :color_hex, :sort_order)
            ON CONFLICT(product_category_id) DO UPDATE SET
                name = excluded.name,
                color_hex = excluded.color_hex,
                sort_order = excluded.sort_order
            """,
            [
                {
                    "product_category_id": slug,
                    "name": label,
                    "color_hex": color,
                    "sort_order": sort_order,
                }
                for slug, label, color, sort_order in PRODUCT_CATEGORIES
            ],
        )


def classify_clover_categories() -> int:
    """Set ``categories.kind`` from Clover category names."""
    updated = 0
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT category_id, name, kind FROM categories"
        ).fetchall()
        for row in rows:
            kind = clover_category_kind(row["name"])
            if row["kind"] == kind:
                continue
            conn.execute(
                "UPDATE categories SET kind = :kind WHERE category_id = :category_id",
                {"kind": kind, "category_id": row["category_id"]},
            )
            updated += 1
    return updated


def derive_item_product_categories() -> int:
    """
    Set ``items.product_category_id`` when Clover assigned a product-type tag.

    Skips items with ``product_category_source='manual'``.
    """
    updated = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT i.item_id, i.product_category_id, i.product_category_source,
                   c.name, c.kind
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE i.is_active = 1
            """
        ).fetchall()

        for row in rows:
            if row["product_category_source"] == "manual":
                continue

            slug = None
            if row["kind"] == "product":
                slug = clover_product_name_to_slug(row["name"])
            elif row["kind"] in ("supplier", "location"):
                slug = None
            elif row["name"]:
                slug = clover_product_name_to_slug(row["name"])

            if slug == row["product_category_id"]:
                continue

            conn.execute(
                """
                UPDATE items
                SET product_category_id = :slug,
                    product_category_source = CASE
                        WHEN :slug IS NOT NULL THEN 'clover'
                        ELSE product_category_source
                    END
                WHERE item_id = :item_id
                  AND (product_category_source IS NULL
                       OR product_category_source != 'manual')
                """,
                {"slug": slug, "item_id": row["item_id"]},
            )
            updated += 1

    return updated
