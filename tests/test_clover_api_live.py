"""
Opt-in live Clover API tests. Not run by default pytest.

Set RUN_CLOVER_API_TESTS=1 and valid .env, then:
    pytest tests/test_clover_api_live.py -v -m live
"""

import os

import pytest

from app.config import Config
from app.clover.client import CloverClient
from app.clover.health_checks import run_battery, summarize

pytestmark = pytest.mark.live

_skip = os.environ.get("RUN_CLOVER_API_TESTS", "").strip() != "1"
_skip_reason = "Set RUN_CLOVER_API_TESTS=1 to hit Clover (read-only, minimal pulls)"


@pytest.mark.skipif(_skip, reason=_skip_reason)
class TestCloverAPILive:
    def test_battery_all_endpoints(self):
        cfg = Config()
        if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
            pytest.skip("CLOVER_API_TOKEN and CLOVER_MERCHANT_ID required in .env")

        client = CloverClient(cfg)
        results = run_battery(client, order_days=7)
        summary = summarize(results)

        failures = [r for r in results if r["status"] != "pass"]
        assert summary["all_pass"], (
            f"Clover API battery failures: "
            + ", ".join(f"{r['name']} ({r['http_status']})" for r in failures)
        )
