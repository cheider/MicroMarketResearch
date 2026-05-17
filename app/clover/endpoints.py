"""
One thin function per Clover resource.
Each function returns raw API dicts and does nothing else.
Transformation and privacy filtering happen in app/etl/transform.py.
"""

from app.clover.paginator import paginate


def fetch_items(client) -> list:
    """Fetches the full item catalog. Returns raw item dicts."""
    results = []
    for page in paginate(client, "items", extra_params={"expand": "itemStock"}):
        results.extend(page)
    return results


def fetch_orders(client, start_ts_ms: int, end_ts_ms: int) -> list:
    """
    Fetches orders within a UTC millisecond timestamp range.
    Orders are returned without line items; caller should use
    fetch_line_items per order for detail.
    """
    results = []
    params = {
        "filter": f"createdTime>={start_ts_ms}&createdTime<={end_ts_ms}",
    }
    for page in paginate(client, "orders", extra_params=params):
        results.extend(page)
    return results


def fetch_line_items(client, order_id: str) -> list:
    """Fetches line items for a single order. Returns raw line item dicts."""
    results = []
    for page in paginate(
        client,
        f"orders/{order_id}/line_items",
        extra_params={"expand": "item"},
    ):
        results.extend(page)
    return results


def fetch_item_stocks(client) -> list:
    """Fetches current stock quantities for all items."""
    results = []
    for page in paginate(client, "item_stocks"):
        results.extend(page)
    return results


def fetch_payments(client, start_ts_ms: int, end_ts_ms: int) -> list:
    """
    Fetches payment records within a UTC millisecond timestamp range.
    Used only for revenue cross-verification; card and tender details
    are dropped by the transform layer before storage.
    """
    results = []
    params = {
        "filter": f"createdTime>={start_ts_ms}&createdTime<={end_ts_ms}",
    }
    for page in paginate(client, "payments", extra_params=params):
        results.extend(page)
    return results
