"""
Run read-only Clover API stress tests from the command line.

Does not write to analytics.db.

Usage:
    python scripts/run_clover_stress.py
    python scripts/run_clover_stress.py --profile standard
    python scripts/run_clover_stress.py --profile heavy --json logs/stress_report.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.clover.client import CloverClient
from app.clover.stress_tests import list_profiles, run_stress_suite


def _print_report(report: dict):
    summary = report["summary"]
    print()
    print(f"Clover stress suite — {report['profile_label']} ({report['profile']})")
    print("-" * 60)
    for row in report["results"]:
        icon = row["status"].upper()
        print(
            f"  [{icon:4}] {row['name']:<32} "
            f"req={row['requests']}  {row['duration_ms']}ms  429={row['http_429']}"
        )
        if row.get("error"):
            print(f"         {row['error']}")
    print("-" * 60)
    print(
        f"  checks: {summary['passed']} pass, {summary['warnings']} warn, "
        f"{summary['failed']} fail"
    )
    print(
        f"  requests: {summary['total_requests']}  "
        f"rate_limits: {summary['rate_limits_hit']}  "
        f"duration: {summary['total_duration_ms']}ms"
    )
    print()


def main():
    parser = argparse.ArgumentParser(description="Clover API stress test runner")
    parser.add_argument(
        "--profile",
        choices=[p["id"] for p in list_profiles()],
        default="light",
        help="Stress profile (default: light)",
    )
    parser.add_argument("--json", default="", help="Write full report JSON to path")
    args = parser.parse_args()

    cfg = Config()
    if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
        print("FAIL: CLOVER_API_TOKEN and CLOVER_MERCHANT_ID required in .env")
        sys.exit(1)

    client = CloverClient(cfg)
    report = run_stress_suite(
        client,
        args.profile,
        client_factory=lambda: CloverClient(cfg),
    )
    report["meta"] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "base_url": cfg.CLOVER_BASE_URL,
        "merchant_id": cfg.CLOVER_MERCHANT_ID,
        "token_set": True,
    }

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote {args.json}")

    _print_report(report)
    sys.exit(0 if report["summary"]["all_pass"] else 1)


if __name__ == "__main__":
    main()
