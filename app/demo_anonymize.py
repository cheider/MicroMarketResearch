"""
Display-layer pseudo-anonymization for safe demos and screenshots.

Does not modify the database. Masks base facts (IDs, units, prices, dates)
deterministically, then derives revenue, margins, and totals so displayed
numbers stay arithmetically consistent (units x price, sums of children, etc.).
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from app.taxonomy import PRODUCT_SLUGS

DEMO_ANONYMIZE_COOKIE = "mmr_demo_anonymize"

_ID_KEYS = frozenset({
    "item_id",
    "category_id",
    "suggested_category_id",
    "merchant_id",
    "order_id",
    "event_id",
})

_SLUG_ID_KEYS = frozenset({
    "product_category_id",
    "suggested_product_category_id",
})

_DATE_KEYS = frozenset({
    "sale_date",
    "week_start",
    "snapshot_ts",
    "start_date",
    "end_date",
    "first_sale_date",
    "last_sale_date",
    "date",
})

# Counts / catalog health — masked independently, not tied to unit-price math.
_COUNT_INT_KEYS = frozenset({
    "active_items",
    "uncategorized",
    "missing_cost",
    "manual_count",
    "suggested_count",
    "clover_count",
    "total_active",
    "count",
    "unassigned_count",
    "not_in_csv_unchanged",
    "updated",
    "moved_to_uncategorized",
    "no_cost_count",
    "total_items",
    "items_with_cost",
    "records_fetched",
})

# Commerce quantities — masked first; revenue is derived from these.
_UNIT_INT_KEYS = frozenset({
    "units_sold",
    "quantity",
    "lifetime_units_sold",
    "on_hand_qty",
    "opening_stock",
    "closing_stock",
    "expected_stock",
    "shrinkage_units",
    "units_sold_90d",
    "total_stock",
    "total_units",
})

_BASE_CENTS_KEYS = frozenset({
    "price_cents",
})

# Never masked directly — always recomputed from masked bases.
_DERIVED_CENTS_KEYS = frozenset({
    "revenue_cents",
    "gross_revenue_cents",
    "total_revenue_cents",
    "gross_profit_cents",
    "total_costs_cents",
    "lifetime_revenue_cents",
    "shrinkage_value_cents",
    "revenue_cents_90d",
    "current_revenue_cents",
    "prior_revenue_cents",
    "total_projected_revenue_cents",
})

_DERIVED_FLOAT_KEYS = frozenset({
    "price_dollars",
    "cost_dollars",
    "lifetime_revenue_dollars",
    "revenue_dollars_90d",
    "margin",
    "margin_pct",
    "profit_margin_pct",
})

_REVENUE_CENTS_KEYS = frozenset({
    "revenue_cents",
    "gross_revenue_cents",
    "lifetime_revenue_cents",
    "revenue_cents_90d",
    "current_revenue_cents",
    "prior_revenue_cents",
    "total_projected_revenue_cents",
})

_PRICE_TIERS = (
    50, 75, 99, 125, 149, 175, 199, 225, 249, 299, 349, 399, 449, 499, 599,
)

_LOREM = (
    "Lorem ipsum",
    "Dolor sit",
    "Amet consectetur",
    "Adipiscing elit",
    "Sed do eiusmod",
)

_DEMO_DATE_BASE = date(2024, 1, 1)

# Realistic retail micro-market gross margins for demo synthesis.
_DEMO_MARGIN_MIN_PCT = 30
_DEMO_MARGIN_MAX_PCT = 60


def use_demo_anonymize(cookie_value: str | None) -> bool:
    return (cookie_value or "").strip() == "1"


def _digest(*parts: str) -> int:
    raw = ":".join(str(p) for p in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def pseudo_id(key: str, value: str) -> str:
    if not value:
        return value
    if key in _SLUG_ID_KEYS and value in PRODUCT_SLUGS:
        return value
    if key == "merchant_id":
        return f"DEMO-MERCH-{_digest('merchant', value) % 100000:05d}"
    prefix = {
        "item_id": "DEMO-ITEM",
        "category_id": "DEMO-CAT",
        "event_id": "DEMO-EVT",
        "order_id": "DEMO-ORD",
        "suggested_category_id": "DEMO-SUG",
    }.get(key, "DEMO-ID")
    return f"{prefix}-{_digest(key, value) % 100000:05d}"


def pseudo_date(value: str) -> str:
    if not value or not isinstance(value, str) or len(value) < 10:
        return value
    offset = _digest("date", value) % 365
    return (_DEMO_DATE_BASE + timedelta(days=offset)).isoformat()


def pseudo_units(seed: str, units: int) -> int:
    if units == 0:
        return 0
    sign = -1 if units < 0 else 1
    units = abs(units)
    lo = max(1, units // 4)
    hi = max(lo + 1, min(units * 2, 80))
    span = max(hi - lo, 1)
    scaled = lo + (_digest("units", seed, str(units)) % span)
    return sign * scaled


def pseudo_price_cents(seed: str, cents: int) -> int:
    if cents == 0:
        return 0
    idx = _digest("price", seed, str(cents)) % len(_PRICE_TIERS)
    return _PRICE_TIERS[idx]


def pseudo_count(seed: str, value: int) -> int:
    if value == 0:
        return 0
    lo = max(1, value // 3)
    hi = max(lo + 1, min(value * 2, 400))
    span = max(hi - lo, 1)
    scaled = lo + (_digest("count", seed, str(value)) % span)
    return -scaled if value < 0 else scaled


def _lorem_label(seed: str) -> str:
    return _LOREM[_digest("lorem", seed) % len(_LOREM)]


def demo_margin_ratio(seed: str) -> float:
    """Deterministic gross-margin ratio in [0.30, 0.60] for demo profit synthesis."""
    span = _DEMO_MARGIN_MAX_PCT - _DEMO_MARGIN_MIN_PCT + 1
    pct = _DEMO_MARGIN_MIN_PCT + (_digest("demo-margin", seed) % span)
    return pct / 100.0


def demo_margin_pct(seed: str) -> float:
    return round(demo_margin_ratio(seed) * 100, 1)


def demo_unit_cost_cents(price_cents: int, seed: str) -> int:
    """Demo-only: derive unit cost from masked price and a deterministic 30–60% margin."""
    if price_cents <= 0:
        return 0
    margin = demo_margin_ratio(seed)
    return max(0, round(price_cents * (1 - margin)))


def margin_pct_from_price_cost(price_cents: int, cost_cents: int) -> float:
    """Gross margin % from price and (derived) cost — used for demo display consistency."""
    if price_cents <= 0:
        return 0.0
    return round((price_cents - cost_cents) / price_cents * 100, 1)


def _needs_demo_derived_cost(orig: dict) -> bool:
    return any(
        k in orig
        for k in (
            "cost_cents",
            "cost_dollars",
            "margin",
            "margin_pct",
            "gross_profit_cents",
            "total_costs_cents",
            "profit_margin_pct",
        )
    )


def _implied_unit_price_cents(orig: dict) -> int:
    for units_key in ("units_sold", "lifetime_units_sold", "quantity", "units_sold_90d"):
        units = orig.get(units_key)
        if units and units > 0:
            for rev_key in _REVENUE_CENTS_KEYS:
                revenue = orig.get(rev_key)
                if revenue and revenue > 0:
                    return max(1, round(revenue / units))
    price = orig.get("price_cents")
    if price and price > 0:
        return int(price)
    return 199


def _resolve_demo_price_cents(out: dict, orig: dict, seed: str) -> int | None:
    price = out.get("price_cents")
    if price is not None:
        return int(price)
    if "price_cents" in orig and orig["price_cents"] is not None:
        price = pseudo_price_cents(seed, int(orig["price_cents"] or 0))
        out["price_cents"] = price
        return price
    if "price_dollars" in orig and orig["price_dollars"] is not None:
        price = pseudo_price_cents(seed, round(float(orig["price_dollars"]) * 100))
        out["price_cents"] = price
        return price
    return None


def _resolve_demo_unit_cost_cents(
    out: dict, orig: dict, seed: str, price_cents: int | None
) -> int | None:
    """
    Demo-only: never mask real cost. When price is known and cost/margin fields
    are present, derive unit cost from price × (1 − random 30–60% margin).
    """
    if price_cents is None or price_cents <= 0 or not _needs_demo_derived_cost(orig):
        return None
    unit_cost = demo_unit_cost_cents(price_cents, seed)
    out["cost_cents"] = unit_cost
    return unit_cost


def _apply_demo_margin_dollars(out: dict, orig: dict, seed: str) -> None:
    price = _resolve_demo_price_cents(out, orig, seed)
    unit_cost = _resolve_demo_unit_cost_cents(out, orig, seed, price)
    if price is None:
        return
    if "price_dollars" in orig:
        out["price_dollars"] = round(price / 100, 2)
    if unit_cost is not None and "cost_dollars" in orig:
        out["cost_dollars"] = round(unit_cost / 100, 2)
    if unit_cost is not None and price > 0:
        calc_margin = margin_pct_from_price_cost(price, unit_cost)
        if "margin_pct" in orig:
            out["margin_pct"] = calc_margin
        if "margin" in orig:
            out["margin"] = round(calc_margin / 100, 4)


def _apply_aggregate_profit_fields(out: dict, orig: dict, seed: str) -> None:
    """Recompute category / weekly profit rows that lack units_sold."""
    if not any(
        k in orig
        for k in ("revenue_cents", "gross_profit_cents", "cost_cents", "margin_pct")
    ):
        return

    if "gross_profit_cents" in orig and not any(
        k in orig for k in ("revenue_cents", "gross_revenue_cents")
    ):
        profit = int(orig.get("gross_profit_cents") or 0)
        if profit <= 0:
            out["gross_profit_cents"] = 0
            return
        masked_profit = pseudo_units(f"{seed}:weekly-profit", max(1, profit // 100)) * 100
        margin = demo_margin_ratio(seed)
        revenue = round(masked_profit / margin) if margin > 0 else masked_profit
        total_cost = max(0, revenue - masked_profit)
        out["gross_profit_cents"] = masked_profit
        if "total_costs_cents" in orig:
            out["total_costs_cents"] = total_cost
        if "margin_pct" in orig and revenue > 0:
            out["margin_pct"] = round(masked_profit / revenue * 100, 1)
        return

    revenue = int(orig.get("revenue_cents") or orig.get("gross_revenue_cents") or 0)
    if revenue <= 0:
        return

    implied_units = max(1, round(revenue / max(_implied_unit_price_cents(orig), 1)))
    units = out.get("units_sold")
    if units is None:
        units = pseudo_units(f"{seed}:agg-units", implied_units)
        out["units_sold"] = units

    unit_price = _resolve_demo_price_cents(out, orig, seed) or pseudo_price_cents(
        seed, _implied_unit_price_cents(orig)
    )
    out["price_cents"] = unit_price
    revenue = int(units) * int(unit_price)
    _set_revenue_fields(out, orig, revenue)

    margin = demo_margin_ratio(seed)
    total_cost = round(revenue * (1 - margin))
    profit = revenue - total_cost

    if "cost_cents" in orig:
        out["cost_cents"] = total_cost
    if "gross_profit_cents" in orig:
        out["gross_profit_cents"] = profit
    if "total_costs_cents" in orig:
        out["total_costs_cents"] = total_cost
    if revenue > 0 and "margin_pct" in orig:
        out["margin_pct"] = round(margin * 100, 1)


def _set_revenue_fields(out: dict, orig: dict, revenue_cents: int) -> None:
    for key in _REVENUE_CENTS_KEYS:
        if key in orig:
            out[key] = revenue_cents
    if "total_revenue_cents" in orig:
        out["total_revenue_cents"] = revenue_cents


def _mask_daily_series(
    labels: list,
    values: list,
    seed: str,
) -> tuple[list, list, list]:
    ref_price = _implied_unit_price_cents({"daily_values": sum(values), "units_sold": max(1, len(values))})
    ref_price = pseudo_price_cents(f"{seed}:daily-ref", ref_price)

    masked_labels: list = []
    masked_values: list = []
    masked_units: list = []

    for i, (label, value) in enumerate(zip(labels, values)):
        day_seed = f"{seed}:{label}:{i}"
        masked_labels.append(pseudo_date(label) if isinstance(label, str) else label)
        if not value:
            masked_values.append(0)
            masked_units.append(0)
            continue
        implied_units = max(1, round(int(value) / max(ref_price, 1)))
        units = pseudo_units(day_seed, implied_units)
        price = pseudo_price_cents(day_seed, ref_price)
        masked_units.append(units)
        masked_values.append(units * price)

    return masked_labels, masked_values, masked_units


def _mask_profit_daily_series(
    labels: list,
    values: list,
    seed: str,
) -> tuple[list, list, list]:
    """Mask a daily gross-profit series while preserving realistic 30–60% margins."""
    margin = demo_margin_ratio(f"{seed}:profit-margin")
    ref_price = pseudo_price_cents(f"{seed}:profit-ref", 199)
    ref_unit_profit = max(1, ref_price - demo_unit_cost_cents(ref_price, f"{seed}:profit-cost"))

    masked_labels: list = []
    masked_values: list = []
    masked_units: list = []

    for i, (label, value) in enumerate(zip(labels, values)):
        day_seed = f"{seed}:profit:{label}:{i}"
        masked_labels.append(pseudo_date(label) if isinstance(label, str) else label)
        if not value:
            masked_values.append(0)
            masked_units.append(0)
            continue
        implied_units = max(1, round(int(value) / ref_unit_profit))
        units = pseudo_units(day_seed, implied_units)
        unit_price = pseudo_price_cents(day_seed, ref_price)
        unit_cost = demo_unit_cost_cents(unit_price, day_seed)
        profit_per_unit = unit_price - unit_cost
        masked_units.append(units)
        masked_values.append(units * profit_per_unit)

    return masked_labels, masked_values, masked_units


def _recompute_row_derivatives(out: dict, orig: dict, seed: str) -> None:
    price = _resolve_demo_price_cents(out, orig, seed)
    unit_cost = _resolve_demo_unit_cost_cents(out, orig, seed, price)

    units = out.get("units_sold")
    if units is None and "units_sold" in orig:
        units = pseudo_units(seed, int(orig.get("units_sold") or 0))
        out["units_sold"] = units

    if units is not None and any(k in orig for k in _REVENUE_CENTS_KEYS):
        unit_price = price if price is not None else pseudo_price_cents(seed, _implied_unit_price_cents(orig))
        revenue = int(units) * int(unit_price)
        _set_revenue_fields(out, orig, revenue)
        price = unit_price
        if unit_cost is None:
            unit_cost = demo_unit_cost_cents(unit_price, seed)
            out["cost_cents"] = unit_cost

    if (
        units is not None
        and unit_cost is not None
        and any(k in orig for k in ("gross_profit_cents", "margin_pct", "profit_margin_pct", "total_costs_cents"))
    ):
        unit_price = price if price is not None else pseudo_price_cents(seed, _implied_unit_price_cents(orig))
        revenue = int(units) * int(unit_price)
        total_cost = int(units) * int(unit_cost)
        profit = revenue - total_cost
        if "gross_profit_cents" in orig:
            out["gross_profit_cents"] = profit
        if "total_costs_cents" in orig:
            out["total_costs_cents"] = total_cost
        if revenue > 0:
            margin = round(profit / revenue * 100, 1)
            if "margin_pct" in orig:
                out["margin_pct"] = margin
            if "profit_margin_pct" in orig:
                out["profit_margin_pct"] = margin

    if "lifetime_units_sold" in out and any(
        k in orig for k in ("lifetime_revenue_cents", "lifetime_revenue_dollars")
    ):
        lu = int(out["lifetime_units_sold"])
        unit_price = price if price is not None else pseudo_price_cents(seed, _implied_unit_price_cents(orig))
        out["lifetime_revenue_cents"] = lu * unit_price
        out["lifetime_revenue_dollars"] = round(out["lifetime_revenue_cents"] / 100, 2)

    if "daily_labels" in orig and "daily_values" in orig:
        is_profit_series = (
            "gross_profit_cents" in orig
            and "total_revenue_cents" not in orig
            and "units_sold" not in orig
        )
        if is_profit_series:
            labels, values, _ = _mask_profit_daily_series(
                list(orig["daily_labels"]),
                list(orig["daily_values"]),
                seed,
            )
            out["daily_labels"] = labels
            out["daily_values"] = values
            if "gross_profit_cents" in orig:
                out["gross_profit_cents"] = sum(values)
            if "total_costs_cents" in orig or "profit_margin_pct" in orig:
                margin = demo_margin_ratio(seed)
                gross = int(out.get("gross_profit_cents") or sum(values))
                revenue = round(gross / margin) if margin > 0 else gross
                if "total_costs_cents" in orig:
                    out["total_costs_cents"] = max(0, revenue - gross)
                if "profit_margin_pct" in orig and revenue > 0:
                    out["profit_margin_pct"] = round(gross / revenue * 100, 1)
        else:
            labels, values, day_units = _mask_daily_series(
                list(orig["daily_labels"]),
                list(orig["daily_values"]),
                seed,
            )
            out["daily_labels"] = labels
            out["daily_values"] = values
            if "total_revenue_cents" in orig:
                out["total_revenue_cents"] = sum(values)
            if "units_sold" in orig:
                out["units_sold"] = sum(day_units)

    elif "total_revenue_cents" in orig and "units_sold" in out and "daily_values" not in orig:
        unit_price = pseudo_price_cents(seed, _implied_unit_price_cents(orig))
        out["total_revenue_cents"] = int(out["units_sold"]) * unit_price

    if (
        "gross_profit_cents" in orig
        and "gross_profit_cents" not in out
        and "daily_values" not in orig
        and "units_sold" not in out
    ):
        _apply_aggregate_profit_fields(out, orig, seed)

    if "opening_stock" in out and "units_sold" in out:
        expected = int(out["opening_stock"]) - int(out["units_sold"])
        if "expected_stock" in orig:
            out["expected_stock"] = expected
        if "closing_stock" in out:
            shrink_units = expected - int(out["closing_stock"])
            if "shrinkage_units" in orig:
                out["shrinkage_units"] = shrink_units
            if "shrinkage_value_cents" in orig:
                cost = unit_cost or out.get("cost_cents") or 0
                out["shrinkage_value_cents"] = shrink_units * int(cost)

    _apply_demo_margin_dollars(out, orig, seed)

    if "revenue_cents_90d" in orig and "units_sold_90d" in out:
        unit_price = price if price is not None else pseudo_price_cents(seed, _implied_unit_price_cents(orig))
        out["revenue_cents_90d"] = int(out["units_sold_90d"]) * int(unit_price)
        if "revenue_dollars_90d" in orig:
            out["revenue_dollars_90d"] = round(out["revenue_cents_90d"] / 100, 2)


def scrub_value(key: str, value: Any, parent_id: str = "") -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if key in _DERIVED_CENTS_KEYS or key in _DERIVED_FLOAT_KEYS:
        return value
    if key in _ID_KEYS and isinstance(value, str):
        return pseudo_id(key, value)
    if key in _DATE_KEYS and isinstance(value, str):
        return pseudo_date(value)
    if key in _BASE_CENTS_KEYS and isinstance(value, int):
        return pseudo_price_cents(f"{parent_id}:{key}", value)
    if key in _UNIT_INT_KEYS and isinstance(value, int):
        return pseudo_units(f"{parent_id}:{key}", value)
    if key in _COUNT_INT_KEYS and isinstance(value, int):
        return pseudo_count(f"{parent_id}:{key}", value)
    if key in ("clover_category", "supplier", "supplier_inferred") and isinstance(value, str):
        val = value.strip()
        if val and val not in ("Unassigned", "None", "—"):
            return _lorem_label(val)
    return value


def scrub_row(row: dict, parent_id: str = "") -> dict:
    if not isinstance(row, dict):
        return row

    orig = row
    seed = str(orig.get("item_id") or parent_id or "row")
    scrub_dimension_name = False
    raw_cat = orig.get("category_id")
    if raw_cat and raw_cat not in PRODUCT_SLUGS and len(str(raw_cat)) > 12:
        scrub_dimension_name = True

    out: dict = {}
    for k, v in orig.items():
        if k in _DERIVED_CENTS_KEYS or k in _DERIVED_FLOAT_KEYS or k in ("cost_cents", "cost_dollars"):
            continue
        if k == "name" and scrub_dimension_name and isinstance(v, str):
            out[k] = _lorem_label(v)
            continue
        if isinstance(v, dict):
            out[k] = scrub_row(v, seed)
        elif isinstance(v, list):
            if k in ("daily_labels", "daily_values", "chart_labels", "chart_revenue", "chart_units"):
                out[k] = deepcopy(v)
            elif k == "values" and v and all(isinstance(x, int) for x in v):
                out[k] = [pseudo_units(f"{seed}:values:{i}", x) for i, x in enumerate(v)]
            else:
                out[k] = scrub_payload(v, seed)
        else:
            out[k] = scrub_value(k, v, seed)

    if orig.get("item_id"):
        out["item_id"] = pseudo_id("item_id", str(orig["item_id"]))

    _recompute_row_derivatives(out, orig, seed)
    return out


def scrub_payload(data: Any, parent_id: str = "") -> Any:
    if isinstance(data, dict):
        return scrub_row(data, parent_id)
    if isinstance(data, list):
        return [scrub_payload(item, parent_id) for item in data]
    if isinstance(data, tuple):
        return tuple(scrub_payload(item, parent_id) for item in data)
    return data


def _reconcile_chart_arrays(ctx: dict) -> None:
    by_product = ctx.get("by_product")
    if not isinstance(by_product, list):
        return
    if "chart_revenue" in ctx:
        ctx["chart_revenue"] = [int(r.get("revenue_cents") or 0) for r in by_product]
    if "chart_units" in ctx:
        ctx["chart_units"] = [int(r.get("units_sold") or 0) for r in by_product]
    if "chart_labels" in ctx:
        ctx["chart_labels"] = [r.get("name", "") for r in by_product]


def _reconcile_stats_from_children(ctx: dict) -> None:
    stats = ctx.get("stats")
    if not isinstance(stats, dict):
        return

    if "daily_values" in stats:
        if "gross_profit_cents" in stats:
            stats["gross_profit_cents"] = sum(int(v) for v in stats["daily_values"])
            margin = demo_margin_ratio("stats-profit")
            gross = int(stats["gross_profit_cents"])
            revenue = round(gross / margin) if margin > 0 else gross
            if "total_costs_cents" in stats:
                stats["total_costs_cents"] = max(0, revenue - gross)
            if "profit_margin_pct" in stats and revenue > 0:
                stats["profit_margin_pct"] = round(gross / revenue * 100, 1)
            if "no_cost_count" in stats:
                stats["no_cost_count"] = 0
        elif "total_revenue_cents" in stats:
            stats["total_revenue_cents"] = sum(int(v) for v in stats["daily_values"])
        return

    child_lists = (
        ctx.get("top_products"),
        ctx.get("by_category"),
        ctx.get("by_product"),
    )
    for rows in child_lists:
        if not isinstance(rows, list) or not rows:
            continue
        if "total_revenue_cents" in stats and all("revenue_cents" in r for r in rows):
            stats["total_revenue_cents"] = sum(int(r.get("revenue_cents") or 0) for r in rows)
        if "units_sold" in stats and all("units_sold" in r for r in rows):
            stats["units_sold"] = sum(int(r.get("units_sold") or 0) for r in rows)
        break


def _reconcile_sales_series_json(ctx: dict) -> None:
    raw = ctx.get("sales_series_json")
    if not raw or not isinstance(raw, str):
        return
    try:
        series = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(series, list):
        return

    seed = "item"
    item = ctx.get("item")
    if isinstance(item, dict) and item.get("item_id"):
        seed = str(item["item_id"])

    masked = []
    for point in series:
        if not isinstance(point, dict):
            masked.append(point)
            continue
        day = point.get("date", "")
        units = pseudo_units(f"{seed}:{day}", int(point.get("units_sold") or 0))
        masked.append({
            "date": pseudo_date(day) if isinstance(day, str) else day,
            "units_sold": units,
        })
    ctx["sales_series_json"] = json.dumps(masked)


def _reconcile_root_totals(ctx: dict) -> None:
    if "total_revenue_cents" in ctx and isinstance(ctx.get("by_product"), list):
        rows = ctx["by_product"]
        if rows:
            ctx["total_revenue_cents"] = sum(int(r.get("revenue_cents") or 0) for r in rows)


def _reconcile_popularity_charts(ctx: dict) -> None:
    for key in ("popularity_overall",):
        chart = ctx.get(key)
        if isinstance(chart, dict) and "labels" in chart:
            chart["labels"] = [pseudo_date(d) if isinstance(d, str) else d for d in chart["labels"]]

    by_category = ctx.get("popularity_by_category")
    if isinstance(by_category, list):
        for block in by_category:
            if isinstance(block, dict) and "labels" in block:
                block["labels"] = [
                    pseudo_date(d) if isinstance(d, str) else d for d in block["labels"]
                ]


def scrub_template_context(context: dict) -> dict:
    ctx = deepcopy(context)
    parent = ""
    if isinstance(ctx.get("item"), dict):
        parent = str(ctx["item"].get("item_id", ""))

    ctx = scrub_payload(ctx, parent)
    _reconcile_chart_arrays(ctx)
    _reconcile_stats_from_children(ctx)
    _reconcile_root_totals(ctx)
    _reconcile_sales_series_json(ctx)
    _reconcile_popularity_charts(ctx)
    return ctx
