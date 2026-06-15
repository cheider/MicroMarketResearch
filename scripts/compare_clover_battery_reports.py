"""
Compare two JSON reports from run_clover_api_battery.py.

Usage:
    python scripts/compare_clover_battery_reports.py logs/a.json logs/b.json
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/compare_clover_battery_reports.py <report_a.json> <report_b.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        a = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        b = json.load(f)

    print("Compare Clover API battery reports")
    print("-" * 60)
    print(f"  A: {sys.argv[1]}")
    print(f"      base_url={a['meta'].get('base_url')}  passed={a['summary']['passed']}/{a['summary']['total']}")
    print(f"  B: {sys.argv[2]}")
    print(f"      base_url={b['meta'].get('base_url')}  passed={b['summary']['passed']}/{b['summary']['total']}")
    print("-" * 60)

    by_name_a = {c["name"]: c for c in a["checks"]}
    by_name_b = {c["name"]: c for c in b["checks"]}

    for name in sorted(set(by_name_a) | set(by_name_b)):
        ra, rb = by_name_a.get(name), by_name_b.get(name)
        sa = ra["status"] if ra else "missing"
        sb = rb["status"] if rb else "missing"
        mark = " " if sa == sb else " *"
        print(f"  {name:<28}  A={sa:<6} B={sb:<6}{mark}")

    print("-" * 60)
    if a["summary"]["all_pass"] != b["summary"]["all_pass"]:
        print("  Overall: different pass/fail between runs")
    else:
        print("  Overall: same pass/fail outcome")


if __name__ == "__main__":
    main()
