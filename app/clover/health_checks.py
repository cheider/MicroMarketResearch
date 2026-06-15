"""
Read-only Clover API health checks for manual or opt-in live testing.

Each check uses minimal page size (limit=1) unless noted.
No POST/PUT/DELETE. No PII in returned result dicts.
"""

from datetime import datetime, timedelta, timezone

from app.clover.client import CloverClient, CloverAPIError
from app.clover.query_params import (
    ITEMS_EXPAND,
    ORDERS_EXPAND,
    created_time_filters,
    merge_params,
    page_params,
)


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _days_ago_ms(days: int) -> int:
    start = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return int(start.timestamp() * 1000)


def _probe(name: str, fn) -> dict:
    try:
        detail = fn()
        return {
            "name": name,
            "status": "pass",
            "http_status": 200,
            "detail": detail,
            "error": None,
        }
    except CloverAPIError as exc:
        return {
            "name": name,
            "status": "fail",
            "http_status": exc.status_code,
            "detail": {},
            "error": str(exc)[:300],
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "fail",
            "http_status": 0,
            "detail": {},
            "error": str(exc)[:300],
        }


def check_items_list(client: CloverClient) -> dict:
    data = client.get("items", params=page_params(limit=1, offset=0))
    elements = data.get("elements") or []
    return {"count_returned": len(elements), "has_more": bool(data.get("href"))}


def check_categories_list(client: CloverClient) -> dict:
    data = client.get("categories", params=page_params(limit=1, offset=0))
    elements = data.get("elements") or []
    return {"count_returned": len(elements)}


def check_item_stocks_list(client: CloverClient) -> dict:
    data = client.get("item_stocks", params=page_params(limit=1, offset=0))
    elements = data.get("elements") or []
    return {"count_returned": len(elements)}


def check_orders_window(client: CloverClient, days: int = 7) -> dict:
    end_ms = _now_ms()
    start_ms = _days_ago_ms(days)
    data = client.get(
        "orders",
        params=merge_params(
            page_params(limit=1, offset=0),
            created_time_filters(start_ms, end_ms),
            ORDERS_EXPAND,
        ),
    )
    elements = data.get("elements") or []
    line_count = 0
    if elements:
        li = (elements[0].get("lineItems") or {}).get("elements") or []
        line_count = len(li)
    return {
        "days": days,
        "orders_returned": len(elements),
        "line_items_on_first_order": line_count,
    }


def check_payments_window(client: CloverClient, days: int = 7) -> dict:
    end_ms = _now_ms()
    start_ms = _days_ago_ms(days)
    data = client.get(
        "payments",
        params=merge_params(
            page_params(limit=1, offset=0),
            created_time_filters(start_ms, end_ms),
        ),
    )
    elements = data.get("elements") or []
    return {"days": days, "payments_returned": len(elements)}


def check_items_with_stock_expand(client: CloverClient) -> dict:
    data = client.get(
        "items",
        params=merge_params(page_params(limit=1, offset=0), ITEMS_EXPAND),
    )
    elements = data.get("elements") or []
    has_stock = False
    if elements and elements[0].get("itemStock") is not None:
        has_stock = True
    return {"count_returned": len(elements), "first_has_itemStock": has_stock}


def check_pagination_second_page(client: CloverClient) -> dict:
    data = client.get("items", params=page_params(limit=1, offset=1))
    return {"offset_1_count": len(data.get("elements") or [])}


def run_battery(client: CloverClient, order_days: int = 7) -> list[dict]:
    """Ordered read-only checks used by scripts and opt-in live tests."""
    return [
        _probe("items_list", lambda: check_items_list(client)),
        _probe("categories_list", lambda: check_categories_list(client)),
        _probe("item_stocks_list", lambda: check_item_stocks_list(client)),
        _probe("items_expand_itemStock", lambda: check_items_with_stock_expand(client)),
        _probe(
            "orders_recent_window",
            lambda: check_orders_window(client, days=order_days),
        ),
        _probe(
            "payments_recent_window",
            lambda: check_payments_window(client, days=order_days),
        ),
        _probe("pagination_offset", lambda: check_pagination_second_page(client)),
    ]


def summarize(results: list[dict]) -> dict:
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = len(results) - passed
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "all_pass": failed == 0,
    }
