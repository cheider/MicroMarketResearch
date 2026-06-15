"""
Manual product-category writes for board, CSV import, and drag-and-drop.
"""

from __future__ import annotations

from app.database import get_connection
from app.taxonomy import PRODUCT_SLUGS


def get_inventory_tools_stats() -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_active,
                SUM(CASE WHEN product_category_id IS NULL
                          AND product_category_source IS DISTINCT FROM 'manual'
                     THEN 1 ELSE 0 END) AS uncategorized,
                SUM(CASE WHEN cost_cents IS NULL THEN 1 ELSE 0 END) AS missing_cost,
                SUM(CASE WHEN product_category_source = 'manual' THEN 1 ELSE 0 END)
                    AS manual_count,
                SUM(CASE WHEN product_category_source = 'suggested' THEN 1 ELSE 0 END)
                    AS suggested_count,
                SUM(CASE WHEN product_category_source = 'clover' THEN 1 ELSE 0 END)
                    AS clover_count
            FROM items
            WHERE is_active = 1
            """
        ).fetchone()
    return {
        "total_active": int(row["total_active"] or 0),
        "uncategorized": int(row["uncategorized"] or 0),
        "missing_cost": int(row["missing_cost"] or 0),
        "manual_count": int(row["manual_count"] or 0),
        "suggested_count": int(row["suggested_count"] or 0),
        "clover_count": int(row["clover_count"] or 0),
    }


def get_category_board_state(
    include_inactive: bool = False,
    hide_modifiers: bool = False,
    search: str = "",
) -> dict:
    clauses = []
    params: dict = {}
    if not include_inactive:
        clauses.append("i.is_active = 1")
    if hide_modifiers:
        clauses.append(
            "(i.product_category_id IS NULL OR i.product_category_id != 'modifiers')"
        )
        clauses.append(
            "(i.suggested_product_category_id IS NULL"
            " OR i.suggested_product_category_id != 'modifiers')"
        )
    if search.strip():
        clauses.append("LOWER(i.name) LIKE :search")
        params["search"] = f"%{search.strip().lower()}%"

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        categories = conn.execute(
            """
            SELECT product_category_id, name, color_hex, sort_order
            FROM product_categories
            ORDER BY COALESCE(sort_order, 999), name
            """
        ).fetchall()

        items = conn.execute(
            f"""
            SELECT
                i.item_id,
                i.name,
                i.price_cents,
                i.is_active,
                i.product_category_id,
                i.suggested_product_category_id,
                i.product_category_source,
                i.category_board_sort,
                c.name AS clover_category_name
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.category_id
            {where}
            ORDER BY COALESCE(i.category_board_sort, 9999), i.name
            """,
            params,
        ).fetchall()

    cat_map = {
        c["product_category_id"]: {
            "product_category_id": c["product_category_id"],
            "name": c["name"],
            "color_hex": c["color_hex"] or "#d1d5db",
            "sort_order": c["sort_order"],
            "chips": [],
        }
        for c in categories
    }
    unassigned: list[dict] = []

    for item in items:
        chip = {
            "item_id": item["item_id"],
            "name": item["name"],
            "price_cents": item["price_cents"],
            "is_active": bool(item["is_active"]),
            "product_category_source": item["product_category_source"],
            "suggested_product_category_id": item["suggested_product_category_id"],
            "sort": item["category_board_sort"],
            "clover_category": item["clover_category_name"],
        }
        slug = item["product_category_id"]
        if slug and slug in cat_map:
            cat_map[slug]["chips"].append(chip)
        else:
            unassigned.append(chip)

    columns = sorted(
        cat_map.values(),
        key=lambda c: (c["sort_order"] if c["sort_order"] is not None else 999, c["name"]),
    )
    for col in columns:
        col["count"] = len(col["chips"])
        col["chips"].sort(
            key=lambda x: (x["sort"] if x["sort"] is not None else 9999, x["name"].lower())
        )

    return {
        "columns": columns,
        "unassigned": sorted(
            unassigned,
            key=lambda x: (x["sort"] if x["sort"] is not None else 9999, x["name"].lower()),
        ),
        "unassigned_count": len(unassigned),
    }


def apply_manual_assignments(assignments: list[dict]) -> dict:
    """
    Batch update from drag-and-drop or API.

    Each assignment: ``item_id``, ``product_category_id`` (slug or null), ``sort``.
    """
    errors = []
    updated = 0

    with get_connection() as conn:
        for entry in assignments:
            item_id = (entry.get("item_id") or "").strip()
            slug = entry.get("product_category_id")
            sort_val = entry.get("sort", 0)

            if not item_id:
                errors.append({"item_id": item_id, "error": "missing item_id"})
                continue

            if slug is not None and slug != "" and slug not in PRODUCT_SLUGS:
                errors.append({
                    "item_id": item_id,
                    "error": f"unknown product_category_id: {slug}",
                })
                continue

            exists = conn.execute(
                "SELECT 1 FROM items WHERE item_id = ?", (item_id,)
            ).fetchone()
            if not exists:
                errors.append({"item_id": item_id, "error": "item not found"})
                continue

            if slug in (None, ""):
                conn.execute(
                    """
                    UPDATE items
                    SET product_category_id = NULL,
                        product_category_source = 'manual',
                        suggested_product_category_id = NULL,
                        category_board_sort = :sort
                    WHERE item_id = :item_id
                    """,
                    {"item_id": item_id, "sort": sort_val},
                )
            else:
                conn.execute(
                    """
                    UPDATE items
                    SET product_category_id = :slug,
                        product_category_source = 'manual',
                        suggested_product_category_id = NULL,
                        category_board_sort = :sort
                    WHERE item_id = :item_id
                    """,
                    {"item_id": item_id, "slug": slug, "sort": sort_val},
                )
            updated += 1

    return {"updated": updated, "errors": errors}


def apply_stored_suggestions() -> dict:
    """
    Promote ``suggested_product_category_id`` to ``product_category_id`` for
    unassigned, non-manual items (board "Apply suggestions" action).
    """
    assignments = []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT item_id, suggested_product_category_id, category_board_sort
            FROM items
            WHERE is_active = 1
              AND suggested_product_category_id IS NOT NULL
              AND product_category_id IS NULL
              AND (product_category_source IS NULL
                   OR product_category_source != 'manual')
            ORDER BY name
            """
        ).fetchall()

    for idx, row in enumerate(rows):
        slug = row["suggested_product_category_id"]
        if slug not in PRODUCT_SLUGS:
            continue
        sort_val = (
            row["category_board_sort"]
            if row["category_board_sort"] is not None
            else idx
        )
        assignments.append({
            "item_id": row["item_id"],
            "product_category_id": slug,
            "sort": sort_val,
        })

    if not assignments:
        return {"updated": 0, "errors": []}
    return apply_manual_assignments(assignments)
