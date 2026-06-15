"""
Which catalog items participate in stock-based analytics.

``track_inventory`` is local metadata (not synced from Clover). Use for
made-to-order cafe drinks, modifiers, and other SKUs without meaningful on-hand qty.
"""


def tracked_items_clause(item_alias: str | None = "i") -> str:
    """SQL fragment: only items that should appear in inventory alerts."""
    if item_alias:
        col = f"{item_alias}.track_inventory"
    else:
        col = "track_inventory"
    return f"AND COALESCE({col}, 1) = 1"
