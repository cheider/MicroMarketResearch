"""
Privacy enforcement layer.

Every raw dict from the Clover API passes through this module before
any persistence occurs. This module operates on explicit allowlists.
Any field not on the allowlist is dropped, not just ignored.

Raw responses are in-memory only. They are never written to disk or
logged in raw form.
"""

import hashlib
from datetime import datetime, timezone
from collections import defaultdict


CATEGORY_SAFE_FIELDS = {"id", "name"}

ITEM_SAFE_FIELDS = {"id", "name", "price", "defaultCost", "isRevenue", "hidden", "itemStock", "categories"}

LINE_ITEM_SAFE_FIELDS = {"id", "item", "quantity", "price", "createdTime"}

STOCK_SAFE_FIELDS = {"item", "quantity", "stockCount"}


def _epoch_ms_to_date(epoch_ms: int) -> str:
    """Converts a Clover millisecond epoch timestamp to a YYYY-MM-DD date string in UTC."""
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def clean_category(raw: dict) -> dict:
    """
    Extracts safe fields from a raw Clover category dict.
    Returns a normalized dict ready for database insertion.
    """
    return {
        "category_id": raw.get("id"),
        "name": raw.get("name", ""),
    }


def _hash_order_id(order_id: str, salt: str) -> str:
    """SHA-256 hash of an order ID with a salt for shrinkage tracing."""
    raw = f"{salt}{order_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def clean_item(raw: dict) -> dict:
    """
    Extracts safe fields from a raw Clover item dict.
    Returns a normalized dict ready for database insertion.
    """
    safe = {k: raw.get(k) for k in ITEM_SAFE_FIELDS if k in raw}

    item_stock = raw.get("itemStock") or {}
    stock_quantity = item_stock.get("quantity") if isinstance(item_stock, dict) else None

    categories = raw.get("categories") or {}
    cat_elements = categories.get("elements", []) if isinstance(categories, dict) else []
    category_id = cat_elements[0].get("id") if cat_elements else None

    return {
        "item_id": safe.get("id"),
        "name": safe.get("name", ""),
        "price_cents": safe.get("price", 0),
        "cost_cents": safe.get("defaultCost"),
        "is_active": 0 if safe.get("hidden") else 1,
        "stock_quantity": stock_quantity,
        "category_id": category_id,
    }


def clean_stock(raw: dict) -> dict:
    """
    Extracts safe fields from a raw Clover item_stocks entry.
    Returns a dict with item_id and quantity only.
    """
    item_ref = raw.get("item") or {}
    item_id = item_ref.get("id") if isinstance(item_ref, dict) else None
    quantity = raw.get("quantity") or raw.get("stockCount") or 0

    return {
        "item_id": item_id,
        "quantity": quantity,
    }


def aggregate_line_items(raw_line_items: list) -> dict:
    """
    Aggregates raw line items into per-item, per-day totals.
    No individual line item rows are returned; only daily sums.
    Raw line items are discarded after aggregation.

    Returns a dict keyed by (item_id, sale_date) with values:
        {"item_id": str, "sale_date": str, "units_sold": int, "gross_revenue_cents": int}
    """
    totals = defaultdict(lambda: {"units_sold": 0, "gross_revenue_cents": 0})

    for raw in raw_line_items:
        safe = {k: raw.get(k) for k in LINE_ITEM_SAFE_FIELDS if k in raw}

        item_ref = safe.get("item") or {}
        item_id = item_ref.get("id") if isinstance(item_ref, dict) else None
        if not item_id:
            continue

        created_ms = safe.get("createdTime")
        if not created_ms:
            continue
        sale_date = _epoch_ms_to_date(int(created_ms))

        quantity = int(safe.get("quantity") or 1)
        price = int(safe.get("price") or 0)

        key = (item_id, sale_date)
        totals[key]["units_sold"] += quantity
        totals[key]["gross_revenue_cents"] += price * quantity

    return {
        key: {
            "item_id": key[0],
            "sale_date": key[1],
            "units_sold": val["units_sold"],
            "gross_revenue_cents": val["gross_revenue_cents"],
        }
        for key, val in totals.items()
    }


def aggregate_payments(raw_payments: list) -> dict:
    """
    Aggregates payment records into a single total revenue figure.
    No card data, tender details, or individual payment rows are returned.
    """
    total = sum(int(p.get("amount", 0)) for p in raw_payments if p.get("result") == "SUCCESS")
    return {"total_revenue_cents": total}
