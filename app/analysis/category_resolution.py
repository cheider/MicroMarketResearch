"""
Resolve **product** category buckets for analytics.

- ``items.category_id`` — raw Clover tag (supplier, location, or legacy product tag)
- ``items.product_category_id`` — normalized product type (Drinks, Snacks, …)
- ``items.suggested_product_category_id`` — local rule-based product type

When "use suggested categories" is on, uncategorized product types appear as
``Drinks (suggested)`` — separate from confirmed ``Drinks``.
"""

from __future__ import annotations

SUGGESTED_PREFIX = "suggested:"
SUGGESTED_CATEGORIES_COOKIE = "mmr_use_suggested_categories"


def use_suggested_categories(cookie_value: str | None) -> bool:
    return (cookie_value or "").strip() == "1"


def parse_category_filter(category_id: str | None) -> tuple[str | None, bool]:
    """``category_id`` in URLs is a **product** category slug (or suggested:slug)."""
    if not category_id:
        return None, False
    if category_id.startswith(SUGGESTED_PREFIX):
        return category_id[len(SUGGESTED_PREFIX):], True
    return category_id, False


def product_bucket_exprs(use_suggested: bool) -> tuple[str, str]:
    """
    SQL (bucket_id, display_name) for product-category reporting.

    Joins: product_categories pc, optional product_categories ps for suggestions.
    """
    if not use_suggested:
        return (
            "COALESCE(i.product_category_id, 'uncategorized')",
            "COALESCE(pc.name, 'Uncategorized')",
        )

    return (
        """
        CASE
            WHEN i.product_category_id IS NOT NULL AND i.product_category_id != ''
                THEN i.product_category_id
            WHEN i.suggested_product_category_id IS NOT NULL
                 AND i.suggested_product_category_id != ''
                THEN 'suggested:' || i.suggested_product_category_id
            ELSE 'uncategorized'
        END
        """.strip(),
        """
        CASE
            WHEN i.product_category_id IS NOT NULL AND i.product_category_id != ''
                THEN COALESCE(pc.name, 'Uncategorized')
            WHEN i.suggested_product_category_id IS NOT NULL
                 AND i.suggested_product_category_id != ''
                THEN COALESCE(ps.name, 'Uncategorized') || ' (suggested)'
            ELSE 'Uncategorized'
        END
        """.strip(),
    )


def product_joins(use_suggested: bool) -> str:
    base = (
        "LEFT JOIN product_categories pc"
        " ON i.product_category_id = pc.product_category_id"
    )
    if use_suggested:
        return base + (
            "\n            LEFT JOIN product_categories ps"
            " ON i.suggested_product_category_id = ps.product_category_id"
        )
    return base


def product_filter_clause(
    category_id: str | None,
    use_suggested: bool,
) -> tuple[str, dict]:
    if not category_id:
        return "", {}

    parsed, is_suggested = parse_category_filter(category_id)
    if is_suggested:
        return (
            "AND (i.product_category_id IS NULL OR i.product_category_id = '') "
            "AND i.suggested_product_category_id = :filter_product_category_id",
            {"filter_product_category_id": parsed},
        )

    return (
        "AND i.product_category_id = :filter_product_category_id",
        {"filter_product_category_id": parsed},
    )


# Backward-compatible aliases used by dashboard_analytics
category_bucket_exprs = product_bucket_exprs
category_joins = product_joins
category_filter_clause = product_filter_clause


def clover_kind_joins() -> str:
    return "LEFT JOIN categories c ON i.category_id = c.category_id"


def clover_dimension_bucket_exprs(kind: str) -> tuple[str, str]:
    """Group by Clover supplier or location tags only."""
    return (
        f"COALESCE(CASE WHEN c.kind = '{kind}' THEN c.category_id END, 'none')",
        f"COALESCE(CASE WHEN c.kind = '{kind}' THEN c.name END, 'Unassigned')",
    )


def clover_dimension_filter(kind: str, clover_category_id: str | None) -> tuple[str, dict]:
    if not clover_category_id:
        return "", {}
    return (
        f"AND c.kind = :clover_kind AND i.category_id = :clover_category_id",
        {"clover_kind": kind, "clover_category_id": clover_category_id},
    )
