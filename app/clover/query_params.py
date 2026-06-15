"""
Clover REST query parameters.

Matches the production PowerShell client pattern:
  limit=1000&offset=0
  filter=createdTime>=START&filter=createdTime<=END  (repeated filter keys)
  expand=itemStock | lineItems | item
"""

from __future__ import annotations

from typing import Any

DEFAULT_PAGE_SIZE = 1000

QueryParams = list[tuple[str, str]]


def page_params(*, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> QueryParams:
    return [("limit", str(limit)), ("offset", str(offset))]


def created_time_filters(start_ms: int, end_ms: int) -> QueryParams:
    return [
        ("filter", f"createdTime>={start_ms}"),
        ("filter", f"createdTime<={end_ms}"),
    ]


def expand_param(name: str) -> QueryParams:
    return [("expand", name)]


def merge_params(*parts: QueryParams) -> QueryParams:
    merged: QueryParams = []
    for part in parts:
        merged.extend(part)
    return merged


def prepare_query_params(
    params: dict[str, Any] | QueryParams | None,
) -> QueryParams | None:
    """
    Normalizes caller params for requests.

    Dict form is supported for health checks and scripts; filter lists become
    repeated ``filter`` query keys (same as Invoke-RestMethod).
    """
    if params is None:
        return None
    if isinstance(params, list):
        return params

    items: QueryParams = []
    for key, value in params.items():
        if value is None:
            continue
        if key == "filter" and isinstance(value, (list, tuple)):
            for clause in value:
                items.append(("filter", str(clause)))
        elif isinstance(value, (list, tuple)):
            for entry in value:
                items.append((key, str(entry)))
        else:
            items.append((key, str(value)))
    return items


# ETL expand flags (see scripts/clover_api_reference.ps1)
ITEMS_EXPAND = merge_params(expand_param("itemStock"), expand_param("categories"))
ORDERS_EXPAND = expand_param("lineItems")
LINE_ITEMS_EXPAND = expand_param("item")
