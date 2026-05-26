"""
Multi-path Clover auth diagnostic (read-only GETs).

Bypasses CloverClient for raw requests; tests merchant root + items on
production and sandbox hosts. Does not print API tokens.

Usage:
    python scripts/probe_clover_auth.py
"""

import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config

BASE_URLS = (
    "https://api.clover.com",
    "https://apisandbox.dev.clover.com",
)

ENDPOINTS = (
    ("merchant_root", ""),
    ("items_limit_1", "items"),
)


def _token_shape_warnings(token: str) -> list[str]:
    warnings = []
    if not token:
        warnings.append("CLOVER_API_TOKEN is empty")
        return warnings
    if token.startswith('"') or token.startswith("'"):
        warnings.append("Token starts with a quote — remove quotes in .env")
    if token.endswith('"') or token.endswith("'"):
        warnings.append("Token ends with a quote — remove quotes in .env")
    if any(c.isspace() for c in token):
        warnings.append("Token contains whitespace")
    if len(token) < 20:
        warnings.append(f"Token unusually short ({len(token)} chars)")
    return warnings


def _merchant_warnings(merchant_id: str) -> list[str]:
    warnings = []
    if not merchant_id:
        warnings.append("CLOVER_MERCHANT_ID is empty")
        return warnings
    if len(merchant_id) != 13:
        warnings.append(
            f"Merchant ID length is {len(merchant_id)} (Clover IDs are usually 13 alphanumeric)"
        )
    if not merchant_id.isalnum():
        warnings.append("Merchant ID contains non-alphanumeric characters")
    return warnings


def _probe_get(base_url: str, merchant_id: str, token: str, subpath: str) -> tuple[int, str]:
    base = base_url.rstrip("/")
    if subpath:
        url = f"{base}/v3/merchants/{merchant_id}/{subpath}"
        params = {"limit": 1} if subpath == "items" else None
    else:
        url = f"{base}/v3/merchants/{merchant_id}"
        params = None
    try:
        resp = requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=(15, 30),
        )
        snippet = (resp.text or "")[:80].replace("\n", " ")
        return resp.status_code, snippet
    except requests.RequestException as exc:
        return 0, str(exc)[:80]


def _recommend(results: list[tuple[str, str, int]]) -> str:
    prod_ok = any(
        status == 200
        for base, _ep, status in results
        if base == "https://api.clover.com"
    )
    sand_ok = any(
        status == 200
        for base, _ep, status in results
        if base == "https://apisandbox.dev.clover.com"
    )
    if prod_ok and not sand_ok:
        return "Use production: set CLOVER_BASE_URL=https://api.clover.com"
    if sand_ok and not prod_ok:
        return "Use sandbox: set CLOVER_BASE_URL=https://apisandbox.dev.clover.com"
    if prod_ok and sand_ok:
        return "Both hosts OK — prefer production for live micro market"
    all_401 = all(status == 401 for _b, _e, status in results if status)
    if all_401 and results:
        return (
            "All 401: regenerate merchant API token for this merchant ID in the "
            "matching Clover dashboard; confirm 13-char merchant ID from URL bar"
        )
    return "No successful path — check warnings above and Clover dashboard token permissions"


def main():
    cfg = Config()
    print("Clover auth probe (read-only)")
    print("-" * 72)
    print(f"  .env base URL:  {cfg.CLOVER_BASE_URL}")
    print(f"  Merchant ID:    {cfg.CLOVER_MERCHANT_ID or '(empty)'}")
    print(f"  Token set:      {'yes' if cfg.CLOVER_API_TOKEN else 'no'}")
    if cfg.CLOVER_API_TOKEN:
        print(f"  Token length:   {len(cfg.CLOVER_API_TOKEN)} chars")

    for w in _token_shape_warnings(cfg.CLOVER_API_TOKEN):
        print(f"  WARN: {w}")
    for w in _merchant_warnings(cfg.CLOVER_MERCHANT_ID):
        print(f"  WARN: {w}")

    if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
        print("\nFAIL: Set CLOVER_API_TOKEN and CLOVER_MERCHANT_ID in .env")
        sys.exit(1)

    print("-" * 72)
    print(f"  {'base_url':<36} {'endpoint':<18} status")
    print("-" * 72)

    matrix: list[tuple[str, str, int]] = []
    for base_url in BASE_URLS:
        for ep_name, subpath in ENDPOINTS:
            status, _body = _probe_get(
                base_url, cfg.CLOVER_MERCHANT_ID, cfg.CLOVER_API_TOKEN, subpath
            )
            matrix.append((base_url, ep_name, status))
            label = f"{base_url.split('//')[1]}"
            print(f"  {label:<36} {ep_name:<18} {status}")

    print("-" * 72)
    print(f"  Recommendation: {_recommend(matrix)}")
    print()

    any_ok = any(s == 200 for _b, _e, s in matrix)
    sys.exit(0 if any_ok else 1)


if __name__ == "__main__":
    main()
