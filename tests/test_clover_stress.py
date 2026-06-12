"""Unit tests for Clover stress suite (mocked — no network)."""

from unittest.mock import MagicMock, patch

import pytest

from app.clover.client import CloverAPIError
from app.clover.stress_tests import (
    list_profiles,
    run_stress_suite,
    summarize_stress,
    _check_sequential_burst,
    _single_get,
)


def test_list_profiles_has_light_standard_heavy():
    ids = {p["id"] for p in list_profiles()}
    assert ids == {"light", "standard", "heavy"}


def test_summarize_stress_counts():
    rows = [
        {"status": "pass", "requests": 5, "http_429": 0, "duration_ms": 10},
        {"status": "warn", "requests": 3, "http_429": 1, "duration_ms": 20},
        {"status": "fail", "requests": 1, "http_429": 0, "duration_ms": 5},
    ]
    s = summarize_stress(rows)
    assert s["passed"] == 1
    assert s["warnings"] == 1
    assert s["failed"] == 1
    assert s["all_pass"] is False
    assert s["total_requests"] == 9
    assert s["rate_limits_hit"] == 1


def test_single_get_success():
    client = MagicMock()
    client.get.return_value = {"elements": [{"id": "a"}]}
    row = _single_get(client, "items")
    assert row["ok"] is True
    assert row["count"] == 1


def test_single_get_api_error():
    client = MagicMock()
    client.get.side_effect = CloverAPIError(401, "Unauthorized")
    row = _single_get(client, "items")
    assert row["ok"] is False
    assert row["http_status"] == 401


def test_sequential_burst_all_pass():
    client = MagicMock()
    client.get.return_value = {"elements": []}
    row = _check_sequential_burst(client, 5)
    assert row["status"] == "pass"
    assert row["requests"] == 5
    assert client.get.call_count == 5


@patch("app.clover.stress_tests.run_battery")
def test_run_stress_suite_light_mocked(mock_battery):
    mock_battery.return_value = [
        {"name": "items_list", "status": "pass", "detail": {}, "error": None}
    ] * 7

    client = MagicMock()
    client.get.return_value = {"elements": []}
    client._config = MagicMock()

    report = run_stress_suite(client, "light", client_factory=lambda: client)
    assert report["profile"] == "light"
    assert report["summary"]["total_checks"] >= 1
    names = [r["name"] for r in report["results"]]
    assert "health_battery" in names
    assert "sequential_item_burst" in names


def test_run_stress_suite_unknown_profile():
    client = MagicMock()
    with pytest.raises(ValueError, match="Unknown profile"):
        run_stress_suite(client, "invalid")
