"""
Verify Clover API credentials without printing secrets.

Usage:
    python scripts/check_clover_connection.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.clover.client import CloverClient, CloverAPIError
from app.clover.query_params import page_params


def _env_warnings(cfg: Config) -> list[str]:
    warnings = []
    token = cfg.CLOVER_API_TOKEN
    mid = cfg.CLOVER_MERCHANT_ID
    if token and (token.startswith(('"', "'")) or token.endswith(('"', "'"))):
        warnings.append("Token looks quoted in .env — remove surrounding quotes")
    if token and any(c.isspace() for c in token):
        warnings.append("Token contains whitespace")
    if mid and len(mid) != 13:
        warnings.append(f"Merchant ID length is {len(mid)} (expected 13 for Clover)")
    return warnings


def main():
    cfg = Config()
    print("Clover connection check")
    print(f"  Base URL:    {cfg.CLOVER_BASE_URL}")
    print(f"  Merchant ID: {cfg.CLOVER_MERCHANT_ID or '(empty)'}")
    print(f"  Token set:   {'yes' if cfg.CLOVER_API_TOKEN else 'no'}")
    if cfg.CLOVER_API_TOKEN:
        print(f"  Token length: {len(cfg.CLOVER_API_TOKEN)} chars")

    if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
        print("\nFAIL: Set CLOVER_API_TOKEN and CLOVER_MERCHANT_ID in .env")
        sys.exit(1)

    for w in _env_warnings(cfg):
        print(f"  WARN: {w}")

    client = CloverClient(cfg)
    try:
        data = client.get("items", params=page_params(limit=1, offset=0))
        n = len(data.get("elements", []))
        print(f"\nOK: Connected. Items endpoint returned {n} row(s).")
    except CloverAPIError as exc:
        print(f"\nFAIL: {exc}")
        if exc.status_code == 401:
            print(
                "  401 usually means token and base URL do not match "
                "(production token + api.clover.com, or sandbox token + apisandbox.dev.clover.com)."
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
