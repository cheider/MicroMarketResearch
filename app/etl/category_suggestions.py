"""
Rule-based **product** category suggestions for items missing a product type.

Suggestions use ``product_categories`` slugs only — never suppliers or locations.
"""

from __future__ import annotations

import re

from app.database import get_connection

# Order matters: modifiers and school_supplies before broader rules.
_PRODUCT_RULES: list[tuple[str, list[str]]] = [
    (
        "modifiers",
        [
            r"\bflavor\b",
            r"\bsauce\b",
            r"alt milk",
            r"extra shot",
            r"\bmodifier\b",
            r"\bpump\b",
            r"\bsyrup\b",
        ],
    ),
    (
        "school_supplies",
        [
            r"\bbook\b",
            r"\bnotebook\b",
            r"\bpencil\b",
            r"\bpen\b",
            r"\bmarker\b",
            r"\bhighlighter\b",
        ],
    ),
    (
        "sandwiches",
        [
            r"\bsandwich\b",
            r"\bwrap\b",
            r"\bpanini\b",
            r"\bhoagie\b",
            r"\bblt\b",
            r"\bclub\b",
        ],
    ),
    (
        "soup",
        [
            r"\bsoup\b",
            r"\bchowder\b",
            r"\bbisque\b",
            r"\bstew\b",
            r"\bramen\b",
            r"\bpho\b",
        ],
    ),
    (
        "salad",
        [
            r"\bsalad\b",
            r"\bcaesar\b",
            r"\bcobb\b",
            r"\bgreens\b",
        ],
    ),
    (
        "drinks",
        [
            r"\blatte\b",
            r"\bamericano\b",
            r"\bmocha\b",
            r"\bchai\b",
            r"\bcappuccino\b",
            r"\bmacchiato\b",
            r"\bcortado\b",
            r"\bespresso\b",
            r"\bsteamer\b",
            r"hot chocolate",
            r"\bitalian soda\b",
            r"\blotus\b",
            r"flat white",
            r"drip coffee",
            r"\bhot tea\b",
            r"white mocha",
            r"\bred bull\b",
            r"\bthirster\b",
            r"\bwater\b",
            r"\bjuice\b",
            r"\bsoda\b",
            r"\b\d+oz\b",
            r"\btea\b",
        ],
    ),
    (
        "prepared_food",
        [
            r"\bbowl\b",
            r"fried rice",
            r"\bgyro\b",
            r"\bmeal\b",
        ],
    ),
    (
        "pastries",
        [
            r"\bcroissant\b",
            r"\bscone\b",
            r"\broll\b",
            r"\bbread\b",
            r"\bpastry\b",
            r"\bmuffin\b",
            r"\bcake\b",
            r"\bcrumble\b",
            r"\bflan\b",
            r"assorted pastries",
            r"carrot cake",
        ],
    ),
    (
        "snacks",
        [
            r"\bcheetos\b",
            r"\bchips\b",
            r"rice krispie",
            r"\bmaruchan\b",
            r"\bpeanuts\b",
            r"\bsnack\b",
            r"\bcandy\b",
            r"\bgranola\b",
            r"\bpopcorn\b",
        ],
    ),
]


def suggest_product_category_slug(
    item_name: str,
    price_cents: int | None = None,
) -> str | None:
    """Return a product category slug, or None."""
    if price_cents is not None and price_cents <= 0:
        modifier_hit = any(
            re.search(pat, (item_name or "").lower())
            for pat in _PRODUCT_RULES[0][1]
        )
        if modifier_hit:
            return "modifiers"

    lower = (item_name or "").lower()
    for slug, patterns in _PRODUCT_RULES:
        for pat in patterns:
            if re.search(pat, lower):
                return slug
    return None


def apply_category_suggestions() -> int:
    """
    Assign ``suggested_product_category_id`` when product type is unknown.

    Skips manual assignments. Clears suggestions once ``product_category_id`` is set.
    """
    updated = 0

    with get_connection() as conn:
        items = conn.execute(
            """
            SELECT item_id, name, price_cents, product_category_id,
                   suggested_product_category_id, product_category_source
            FROM items
            WHERE is_active = 1
            """
        ).fetchall()

        for row in items:
            if row["product_category_source"] == "manual":
                continue

            item_id = row["item_id"]
            official = (row["product_category_id"] or "").strip()

            if official:
                if row["suggested_product_category_id"]:
                    conn.execute(
                        """
                        UPDATE items
                        SET suggested_product_category_id = NULL
                        WHERE item_id = ?
                        """,
                        (item_id,),
                    )
                    updated += 1
                continue

            suggested = suggest_product_category_slug(
                row["name"],
                row["price_cents"],
            )
            if suggested == row["suggested_product_category_id"]:
                continue

            conn.execute(
                """
                UPDATE items
                SET suggested_product_category_id = :suggested
                WHERE item_id = :item_id
                """,
                {"item_id": item_id, "suggested": suggested},
            )
            updated += 1

    return updated
