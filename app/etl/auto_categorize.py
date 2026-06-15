"""
Auto-categorize items using string-find rules (preview + apply).
"""

from __future__ import annotations

from app.database import get_connection
from app.etl.category_suggestions import _PRODUCT_RULES, suggest_product_category_slug


def _rule_label_for_slug(slug: str) -> str:
    for s, patterns in _PRODUCT_RULES:
        if s == slug:
            return patterns[0] if patterns else slug
    return slug


def preview_auto_categorize(only_unassigned: bool = True) -> list[dict]:
    """Items that would change under rule-based categorization."""
    rows_out = []
    with get_connection() as conn:
        items = conn.execute(
            """
            SELECT item_id, name, price_cents, product_category_id,
                   suggested_product_category_id, product_category_source
            FROM items
            WHERE is_active = 1
            ORDER BY name
            """
        ).fetchall()

    for row in items:
        if row["product_category_source"] == "manual":
            continue
        current = row["product_category_id"] or row["suggested_product_category_id"]
        if only_unassigned and current:
            continue

        suggested = suggest_product_category_slug(row["name"], row["price_cents"])
        if not suggested or suggested == current:
            continue

        rows_out.append({
            "item_id": row["item_id"],
            "name": row["name"],
            "current": current,
            "suggested": suggested,
            "rule_matched": _rule_label_for_slug(suggested),
        })
    return rows_out


def apply_auto_categorize(
    only_unassigned: bool = True,
    write_as_suggested: bool = False,
) -> int:
    """
    Apply rule-based categories.

    By default writes ``suggested_product_category_id``.
    If ``write_as_suggested=False``, sets ``product_category_id`` with source ``suggested``.
    """
    updated = 0
    previews = preview_auto_categorize(only_unassigned=only_unassigned)

    with get_connection() as conn:
        for row in previews:
            if write_as_suggested:
                conn.execute(
                    """
                    UPDATE items
                    SET suggested_product_category_id = :slug
                    WHERE item_id = :item_id
                      AND (product_category_source IS NULL
                           OR product_category_source != 'manual')
                    """,
                    {"slug": row["suggested"], "item_id": row["item_id"]},
                )
            else:
                conn.execute(
                    """
                    UPDATE items
                    SET product_category_id = :slug,
                        product_category_source = 'suggested',
                        suggested_product_category_id = NULL
                    WHERE item_id = :item_id
                      AND (product_category_source IS NULL
                           OR product_category_source != 'manual')
                    """,
                    {"slug": row["suggested"], "item_id": row["item_id"]},
                )
            updated += 1
    return updated
