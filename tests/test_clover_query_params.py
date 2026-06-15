"""Unit tests for Clover query param builders (no network)."""

import requests

from app.clover.query_params import (
    DEFAULT_PAGE_SIZE,
    ITEMS_EXPAND,
    ORDERS_EXPAND,
    created_time_filters,
    merge_params,
    page_params,
    prepare_query_params,
)


def _url(path: str, params) -> str:
    return requests.Request("GET", f"https://api.clover.com/v3/merchants/MID/{path}", params=params).prepare().url


def test_default_page_size_is_1000():
    assert DEFAULT_PAGE_SIZE == 1000


def test_page_params():
    assert page_params() == [("limit", "1000"), ("offset", "0")]


def test_created_time_filters_repeat_filter_key():
    params = created_time_filters(1748649600000, 1748735999000)
    url = _url("orders", params)
    assert "filter=createdTime%3E%3D1748649600000" in url
    assert "filter=createdTime%3C%3D1748735999000" in url


def test_orders_params_match_powershell_reference():
    params = merge_params(
        page_params(limit=1000, offset=0),
        created_time_filters(1748649600000, 1748735999000),
        ORDERS_EXPAND,
    )
    url = _url("orders", params)
    assert "limit=1000" in url
    assert "offset=0" in url
    assert "expand=lineItems" in url
    assert url.count("filter=") == 2


def test_items_params_match_powershell_reference():
    params = merge_params(page_params(limit=1000, offset=0), ITEMS_EXPAND)
    url = _url("items", params)
    assert "limit=1000" in url
    assert "offset=0" in url
    assert "expand=itemStock" in url
    assert "expand=categories" in url


def test_prepare_query_params_from_dict():
    params = prepare_query_params(
        {
            "limit": 1,
            "filter": ["createdTime>=1", "createdTime<=2"],
            "expand": "lineItems",
        }
    )
    url = _url("orders", params)
    assert "limit=1" in url
    assert url.count("filter=") == 2
    assert "expand=lineItems" in url
