"""
NSC Micro Market taxonomy — Clover "categories" mix three concepts.

Clover category names are classified locally (never sent back to Clover):

- **product**  — what the item is (Drinks, Snacks, Pastries, …)
- **supplier** — who fulfills/stocks it (US Foods, Snak Club, Harried & Hungry)
- **location** — which register/shop sold it (Lily Pad Cafe, Bookstore)

Dashboard "Sales by Category" uses **product** categories only.
``items.category_id`` keeps the raw Clover tag for supplier/location reporting.
"""

from __future__ import annotations

# slug, display name, board color, sort order
PRODUCT_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    ("drinks", "Drinks", "#4f8ef7", 1),
    ("snacks", "Snacks", "#f59e0b", 2),
    ("pastries", "Pastries", "#ec4899", 3),
    ("sandwiches", "Sandwiches", "#14b8a6", 4),
    ("soup", "Soup", "#f97316", 5),
    ("salad", "Salad", "#22c55e", 6),
    ("prepared_food", "Prepared Food", "#8b5cf6", 7),
    ("school_supplies", "School Supplies", "#6366f1", 8),
    ("modifiers", "Modifiers", "#9ca3af", 9),
    ("uncategorized", "Uncategorized", "#d1d5db", 10),
    ("other", "Other", "#6b7280", 11),
)

PRODUCT_SLUGS = frozenset(s for s, _, _, _ in PRODUCT_CATEGORIES)

CAFE_PRODUCT_SLUGS = frozenset({
    "drinks", "modifiers", "prepared_food", "sandwiches", "soup", "salad",
})

SUPPLIER_NAMES = frozenset({
    "snak club",
    "harried & hungry",
    "harried and hungry",
    "us foods",
})

LOCATION_NAMES = frozenset({
    "lily pad cafe",
    "bookstore",
})

# Legacy Clover product-type category names only
PRODUCT_NAMES = frozenset({
    "drinks",
    "snacks",
    "pastries",
})

PRODUCT_CATEGORY_SOURCES = frozenset({"clover", "suggested", "manual"})


def normalize_name(name: str | None) -> str:
    return (name or "").strip().lower()


def clover_category_kind(name: str | None) -> str:
    """
    Returns: ``product`` | ``supplier`` | ``location`` | ``unknown``
    """
    key = normalize_name(name)
    if key in PRODUCT_NAMES:
        return "product"
    if key in SUPPLIER_NAMES:
        return "supplier"
    if key in LOCATION_NAMES:
        return "location"
    return "unknown"


def clover_product_name_to_slug(name: str | None) -> str | None:
    """Map a Clover product-category name to a local slug."""
    key = normalize_name(name)
    if key == "drinks":
        return "drinks"
    if key == "snacks":
        return "snacks"
    if key == "pastries":
        return "pastries"
    return None


def product_slug_for_name(display_name: str) -> str | None:
    for slug, label, _, _ in PRODUCT_CATEGORIES:
        if label.lower() == display_name.strip().lower():
            return slug
    return None


def product_category_meta(slug: str) -> dict | None:
    for s, label, color, sort_order in PRODUCT_CATEGORIES:
        if s == slug:
            return {
                "product_category_id": s,
                "name": label,
                "color_hex": color,
                "sort_order": sort_order,
            }
    return None
