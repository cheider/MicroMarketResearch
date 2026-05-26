"""Unit tests for Clover health_checks (mocked — no network)."""

from unittest.mock import MagicMock

from app.clover.health_checks import (
    check_items_list,
    run_battery,
    summarize,
    _probe,
)
from app.clover.client import CloverAPIError


def test_check_items_list_returns_count():
    client = MagicMock()
    client.get.return_value = {"elements": [{"id": "x"}], "href": "/next"}
    detail = check_items_list(client)
    assert detail["count_returned"] == 1
    assert detail["has_more"] is True


def test_probe_captures_api_error():
    def boom():
        raise CloverAPIError(401, "Unauthorized")

    row = _probe("bad", boom)
    assert row["status"] == "fail"
    assert row["http_status"] == 401


def test_run_battery_all_pass_with_mock():
    client = MagicMock()
    client.get.return_value = {"elements": []}
    results = run_battery(client, order_days=7)
    assert len(results) == 7
    assert summarize(results)["all_pass"] is True
