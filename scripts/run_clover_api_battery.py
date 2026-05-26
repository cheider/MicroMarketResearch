"""
Read-only Clover API test battery (minimal API pulls).

Does not write to analytics.db. Does not log tokens or response bodies with PII.

Usage:
    python scripts/run_clover_api_battery.py
    python scripts/run_clover_api_battery.py --days 14
    python scripts/run_clover_api_battery.py --json logs/clover_battery_report.json

Exit code 0 if all checks pass, 1 otherwise.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.clover.client import CloverClient
from app.clover.health_checks import run_battery, summarize


def _print_table(results: list[dict], summary: dict, meta: dict):
    print()
    print("Clover API battery")
    print("-" * 60)
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print("-" * 60)
    for row in results:
        icon = "PASS" if row["status"] == "pass" else "FAIL"
        detail = json.dumps(row["detail"], separators=(",", ":")) if row["detail"] else ""
        err = f"  |  {row['error']}" if row.get("error") else ""
        print(f"  [{icon}] {row['name']:<28} {detail}{err}")
    print("-" * 60)
    print(f"  {summary['passed']}/{summary['total']} passed")
    print()


def main():
    parser = argparse.ArgumentParser(description="Run read-only Clover API health battery.")
    parser.add_argument("--days", type=int, default=7, help="Order/payment lookback window")
    parser.add_argument("--json", type=str, default="", help="Write JSON report to this path")
    parser.add_argument(
        "--base-url",
        type=str,
        default="",
        help="Override CLOVER_BASE_URL for this run only (e.g. sandbox diagnostic)",
    )
    args = parser.parse_args()

    cfg = Config()
    if args.base_url:
        object.__setattr__(cfg, "CLOVER_BASE_URL", args.base_url.rstrip("/"))
    meta = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "base_url": cfg.CLOVER_BASE_URL,
        "merchant_id": cfg.CLOVER_MERCHANT_ID or "(empty)",
        "token_set": bool(cfg.CLOVER_API_TOKEN),
        "order_payment_days": args.days,
    }

    if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
        print("FAIL: CLOVER_API_TOKEN and CLOVER_MERCHANT_ID required in .env")
        sys.exit(1)

    client = CloverClient(cfg)
    results = run_battery(client, order_days=args.days)
    summary = summarize(results)

    report = {"meta": meta, "summary": summary, "checks": results}

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote report to {args.json}")

    _print_table(results, summary, meta)
    sys.exit(0 if summary["all_pass"] else 1)


if __name__ == "__main__":
    main()
