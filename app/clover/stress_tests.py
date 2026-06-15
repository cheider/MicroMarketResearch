"""
Read-only Clover API stress / load checks.

Simulates ingest-style traffic (pagination, bursts, parallel GETs) without
writing to analytics.db or logging response bodies.

Profiles:
  light    — quick UI smoke (~15–30 requests)
  standard — moderate pagination + parallel burst
  heavy    — larger catalog pages + higher concurrency (use sparingly)
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.clover.client import CloverAPIError, CloverClient, CloverRateLimitError
from app.clover.health_checks import run_battery, summarize
from app.clover.paginator import paginate
from app.clover.query_params import (
    ITEMS_EXPAND,
    ORDERS_EXPAND,
    created_time_filters,
    merge_params,
    page_params,
)

ProgressCallback = Callable[[str, str, dict | None], None]

PROFILES: dict[str, dict] = {
    "light": {
        "label": "Light (quick)",
        "description": "Health battery plus a short burst of item requests.",
        "run_battery": True,
        "battery_days": 7,
        "sequential_item_requests": 10,
        "parallel_workers": 0,
        "parallel_requests_per_worker": 0,
        "max_pages": {"categories": 1, "items": 2, "item_stocks": 1, "orders": 1},
        "order_days": 7,
        "round_robin_cycles": 2,
    },
    "standard": {
        "label": "Standard",
        "description": "Multi-page catalog pull, parallel burst, and ingest-style round-robin.",
        "run_battery": True,
        "battery_days": 14,
        "sequential_item_requests": 20,
        "parallel_workers": 4,
        "parallel_requests_per_worker": 5,
        "max_pages": {"categories": 3, "items": 5, "item_stocks": 3, "orders": 2},
        "order_days": 30,
        "round_robin_cycles": 3,
    },
    "heavy": {
        "label": "Heavy",
        "description": "High page counts and concurrency — may trigger rate limits (retries expected).",
        "run_battery": True,
        "battery_days": 30,
        "sequential_item_requests": 40,
        "parallel_workers": 8,
        "parallel_requests_per_worker": 8,
        "max_pages": {"categories": 10, "items": 15, "item_stocks": 10, "orders": 5},
        "order_days": 90,
        "round_robin_cycles": 5,
    },
}


def list_profiles() -> list[dict]:
    return [
        {
            "id": pid,
            "label": cfg["label"],
            "description": cfg["description"],
        }
        for pid, cfg in PROFILES.items()
    ]


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _days_ago_ms(days: int) -> int:
    start = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return int(start.timestamp() * 1000)


def _result(
    name: str,
    status: str,
    *,
    duration_ms: float = 0,
    requests: int = 0,
    http_429: int = 0,
    detail: dict | None = None,
    error: str | None = None,
) -> dict:
    return {
        "name": name,
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "requests": requests,
        "http_429": http_429,
        "detail": detail or {},
        "error": (error or "")[:300] or None,
    }


def _single_get(client: CloverClient, path: str, params=None) -> dict:
    start = time.perf_counter()
    try:
        data = client.get(path, params=params)
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "ok": True,
            "http_status": 200,
            "duration_ms": elapsed,
            "count": len(data.get("elements") or []),
            "http_429": 0,
        }
    except CloverRateLimitError:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "ok": True,
            "http_status": 429,
            "duration_ms": elapsed,
            "count": 0,
            "http_429": 1,
            "recovered": True,
        }
    except CloverAPIError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "ok": False,
            "http_status": exc.status_code,
            "duration_ms": elapsed,
            "count": 0,
            "http_429": 1 if exc.status_code == 429 else 0,
            "error": str(exc),
        }


def _check_battery(client: CloverClient, days: int) -> dict:
    start = time.perf_counter()
    rows = run_battery(client, order_days=days)
    summary = summarize(rows)
    elapsed = (time.perf_counter() - start) * 1000
    failed = [r for r in rows if r["status"] != "pass"]
    status = "pass" if summary["all_pass"] else "fail"
    return _result(
        "health_battery",
        status,
        duration_ms=elapsed,
        requests=summary["total"],
        detail={
            "passed": summary["passed"],
            "total": summary["total"],
            "failed_checks": [r["name"] for r in failed],
        },
        error=None if summary["all_pass"] else "One or more health checks failed",
    )


def _check_sequential_burst(client: CloverClient, count: int) -> dict:
    start = time.perf_counter()
    ok = 0
    failed = 0
    rate_limits = 0
    latencies: list[float] = []

    for _ in range(count):
        row = _single_get(client, "items", params=page_params(limit=1, offset=0))
        latencies.append(row["duration_ms"])
        rate_limits += row.get("http_429", 0)
        if row["ok"]:
            ok += 1
        else:
            failed += 1

    elapsed = (time.perf_counter() - start) * 1000
    status = "pass" if failed == 0 else "fail"
    if failed == 0 and rate_limits > 0:
        status = "warn"
    return _result(
        "sequential_item_burst",
        status,
        duration_ms=elapsed,
        requests=count,
        http_429=rate_limits,
        detail={
            "successes": ok,
            "failures": failed,
            "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "max_ms": round(max(latencies), 1) if latencies else 0,
        },
        error=f"{failed} request(s) failed" if failed else None,
    )


def _check_parallel_burst(
    client_factory: Callable[[], CloverClient],
    workers: int,
    per_worker: int,
) -> dict:
    start = time.perf_counter()
    total = workers * per_worker
    ok = 0
    failed = 0
    rate_limits = 0
    latencies: list[float] = []

    def _worker_task(_idx: int) -> list[dict]:
        c = client_factory()
        return [
            _single_get(c, "items", params=page_params(limit=1, offset=0))
            for _ in range(per_worker)
        ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker_task, i) for i in range(workers)]
        for fut in as_completed(futures):
            for row in fut.result():
                latencies.append(row["duration_ms"])
                rate_limits += row.get("http_429", 0)
                if row["ok"]:
                    ok += 1
                else:
                    failed += 1

    elapsed = (time.perf_counter() - start) * 1000
    status = "pass" if failed == 0 else "fail"
    if failed == 0 and rate_limits > 0:
        status = "warn"
    return _result(
        "parallel_item_burst",
        status,
        duration_ms=elapsed,
        requests=total,
        http_429=rate_limits,
        detail={
            "workers": workers,
            "per_worker": per_worker,
            "successes": ok,
            "failures": failed,
            "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        },
        error=f"{failed} request(s) failed" if failed else None,
    )


def _check_pagination(
    client: CloverClient,
    path: str,
    *,
    max_pages: int,
    extra_params=None,
) -> dict:
    start = time.perf_counter()
    pages = 0
    elements = 0
    rate_limits = 0

    try:
        for page in paginate(client, path, extra_params=extra_params or []):
            pages += 1
            elements += len(page)
            if pages >= max_pages:
                break
    except CloverRateLimitError:
        rate_limits += 1
        status = "warn"
        elapsed = (time.perf_counter() - start) * 1000
        return _result(
            f"pagination_{path.replace('/', '_')}",
            status,
            duration_ms=elapsed,
            requests=pages,
            http_429=rate_limits,
            detail={"pages_fetched": pages, "elements": elements, "max_pages": max_pages},
            error="Rate limit after retries",
        )
    except CloverAPIError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return _result(
            f"pagination_{path.replace('/', '_')}",
            "fail",
            duration_ms=elapsed,
            requests=pages,
            http_429=1 if exc.status_code == 429 else 0,
            detail={"pages_fetched": pages, "elements": elements},
            error=str(exc)[:300],
        )

    elapsed = (time.perf_counter() - start) * 1000
    return _result(
        f"pagination_{path.replace('/', '_')}",
        "pass",
        duration_ms=elapsed,
        requests=pages,
        detail={"pages_fetched": pages, "elements": elements, "max_pages": max_pages},
    )


def _check_orders_pagination(client: CloverClient, *, max_pages: int, days: int) -> dict:
    start_ms = _days_ago_ms(days)
    end_ms = _now_ms()
    extra = merge_params(created_time_filters(start_ms, end_ms), ORDERS_EXPAND)
    return _check_pagination(client, "orders", max_pages=max_pages, extra_params=extra)


def _check_ingest_round_robin(client: CloverClient, cycles: int, order_days: int) -> dict:
    """Hits the same endpoints ingest uses, in rotation."""
    start_ms = _days_ago_ms(order_days)
    end_ms = _now_ms()
    order_params = merge_params(
        page_params(limit=1000, offset=0),
        created_time_filters(start_ms, end_ms),
        ORDERS_EXPAND,
    )
    endpoints = [
        ("categories", page_params(limit=1000, offset=0)),
        ("items", merge_params(page_params(limit=1000, offset=0), ITEMS_EXPAND)),
        ("item_stocks", page_params(limit=1000, offset=0)),
        ("orders", order_params),
    ]

    start = time.perf_counter()
    ok = 0
    failed = 0
    rate_limits = 0
    total_requests = 0

    for _ in range(cycles):
        for path, params in endpoints:
            total_requests += 1
            row = _single_get(client, path, params=params)
            rate_limits += row.get("http_429", 0)
            if row["ok"]:
                ok += 1
            else:
                failed += 1

    elapsed = (time.perf_counter() - start) * 1000
    status = "pass" if failed == 0 else "fail"
    if failed == 0 and rate_limits > 0:
        status = "warn"
    return _result(
        "ingest_endpoint_round_robin",
        status,
        duration_ms=elapsed,
        requests=total_requests,
        http_429=rate_limits,
        detail={"cycles": cycles, "successes": ok, "failures": failed},
        error=f"{failed} request(s) failed" if failed else None,
    )


def summarize_stress(results: list[dict]) -> dict:
    passed = sum(1 for r in results if r["status"] == "pass")
    warned = sum(1 for r in results if r["status"] == "warn")
    failed = sum(1 for r in results if r["status"] == "fail")
    return {
        "total_checks": len(results),
        "passed": passed,
        "warnings": warned,
        "failed": failed,
        "all_pass": failed == 0,
        "total_requests": sum(r.get("requests", 0) for r in results),
        "rate_limits_hit": sum(r.get("http_429", 0) for r in results),
        "total_duration_ms": round(sum(r.get("duration_ms", 0) for r in results), 1),
    }


def run_stress_suite(
    client: CloverClient,
    profile: str = "light",
    *,
    on_progress: ProgressCallback | None = None,
    client_factory: Callable[[], CloverClient] | None = None,
) -> dict:
    """
    Run a stress profile. Returns {profile, results, summary}.

    client_factory builds fresh clients for parallel workers (defaults to
    reusing the same config as ``client``).
    """
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; choose from {list(PROFILES)}")

    cfg = PROFILES[profile]
    if client_factory is None:
        cfg = getattr(client, "_config", None)
        client_factory = (lambda: CloverClient(cfg)) if cfg is not None else (lambda: client)

    results: list[dict] = []

    def _notify(name: str, status: str, detail: dict | None = None):
        if on_progress:
            on_progress(name, status, detail)

    if cfg.get("run_battery"):
        _notify("health_battery", "running")
        row = _check_battery(client, cfg.get("battery_days", 7))
        results.append(row)
        _notify("health_battery", row["status"], row)

    seq = cfg.get("sequential_item_requests", 0)
    if seq > 0:
        _notify("sequential_item_burst", "running")
        row = _check_sequential_burst(client, seq)
        results.append(row)
        _notify("sequential_item_burst", row["status"], row)

    workers = cfg.get("parallel_workers", 0)
    per_worker = cfg.get("parallel_requests_per_worker", 0)
    if workers > 0 and per_worker > 0:
        _notify("parallel_item_burst", "running")
        row = _check_parallel_burst(client_factory, workers, per_worker)
        results.append(row)
        _notify("parallel_item_burst", row["status"], row)

    max_pages = cfg.get("max_pages", {})
    for resource, pages in max_pages.items():
        if pages <= 0:
            continue
        name = f"pagination_{resource}"
        _notify(name, "running")
        if resource == "orders":
            row = _check_orders_pagination(
                client, max_pages=pages, days=cfg.get("order_days", 7)
            )
        elif resource == "items":
            row = _check_pagination(
                client, "items", max_pages=pages, extra_params=ITEMS_EXPAND
            )
        else:
            row = _check_pagination(client, resource, max_pages=pages)
        results.append(row)
        _notify(name, row["status"], row)

    cycles = cfg.get("round_robin_cycles", 0)
    if cycles > 0:
        _notify("ingest_endpoint_round_robin", "running")
        row = _check_ingest_round_robin(
            client, cycles, cfg.get("order_days", 7)
        )
        results.append(row)
        _notify("ingest_endpoint_round_robin", row["status"], row)

    summary = summarize_stress(results)
    return {
        "profile": profile,
        "profile_label": cfg["label"],
        "results": results,
        "summary": summary,
    }
