"""Tests for demo anonymization display filter."""

from app.demo_anonymize import (
    pseudo_id,
    scrub_payload,
    scrub_template_context,
    use_demo_anonymize,
)


def test_use_demo_anonymize_cookie():
    assert use_demo_anonymize("1") is True
    assert use_demo_anonymize("0") is False
    assert use_demo_anonymize(None) is False


def test_pseudo_item_id_is_deterministic():
    a = pseudo_id("item_id", "ABC123REAL")
    b = pseudo_id("item_id", "ABC123REAL")
    c = pseudo_id("item_id", "OTHER")
    assert a == b
    assert a != c
    assert a.startswith("DEMO-ITEM-")


def test_scrub_preserves_item_name():
    row = {"item_id": "REAL1", "name": "Extra Gum", "price_cents": 125}
    out = scrub_payload([row])[0]
    assert out["name"] == "Extra Gum"
    assert out["item_id"].startswith("DEMO-ITEM-")
    assert out["price_cents"] != 125


def test_scrub_preserves_product_type_slug():
    row = {"product_category_id": "snacks", "name": "Snacks"}
    out = scrub_payload([row])[0]
    assert out["product_category_id"] == "snacks"
    assert out["name"] == "Snacks"


def test_revenue_equals_units_times_price():
    row = {
        "item_id": "GUM1",
        "name": "Extra Gum",
        "units_sold": 10,
        "price_cents": 125,
        "revenue_cents": 1250,
    }
    out = scrub_payload([row])[0]
    assert out["revenue_cents"] == out["units_sold"] * out["price_cents"]


def test_implied_unit_price_when_price_missing():
    row = {
        "item_id": "LATTE1",
        "name": "Latte",
        "units_sold": 5,
        "revenue_cents": 1750,
    }
    out = scrub_payload([row])[0]
    assert out["revenue_cents"] % out["units_sold"] == 0


def test_stats_total_matches_daily_values_sum():
    ctx = scrub_template_context({
        "stats": {
            "total_revenue_cents": 50000,
            "units_sold": 120,
            "daily_labels": ["2026-06-01", "2026-06-02", "2026-06-03"],
            "daily_values": [20000, 15000, 15000],
        },
    })
    stats = ctx["stats"]
    assert stats["total_revenue_cents"] == sum(stats["daily_values"])
    assert all(label.startswith("2024-") for label in stats["daily_labels"])


def test_stats_total_matches_top_products_sum():
    ctx = scrub_template_context({
        "stats": {"total_revenue_cents": 9000, "units_sold": 30},
        "top_products": [
            {"item_id": "A", "name": "Chips", "units_sold": 10, "revenue_cents": 5000},
            {"item_id": "B", "name": "Water", "units_sold": 20, "revenue_cents": 4000},
        ],
    })
    stats = ctx["stats"]
    products = ctx["top_products"]
    assert stats["total_revenue_cents"] == sum(p["revenue_cents"] for p in products)
    assert stats["units_sold"] == sum(p["units_sold"] for p in products)
    for p in products:
        assert p["revenue_cents"] % max(p["units_sold"], 1) == 0


def test_chart_revenue_synced_with_by_product():
    ctx = scrub_template_context({
        "by_product": [
            {"name": "Snacks", "units_sold": 8, "revenue_cents": 800},
            {"name": "Drinks", "units_sold": 4, "revenue_cents": 1200},
        ],
        "chart_revenue": [800, 1200],
        "chart_labels": ["Snacks", "Drinks"],
    })
    assert ctx["chart_revenue"] == [
        row["revenue_cents"] for row in ctx["by_product"]
    ]


def test_item_lifetime_revenue_consistent():
    ctx = scrub_template_context({
        "item": {
            "item_id": "X1",
            "name": "Cookie",
            "price_cents": 199,
            "lifetime_units_sold": 42,
            "lifetime_revenue_cents": 8358,
            "lifetime_revenue_dollars": 83.58,
            "first_sale_date": "2026-01-15",
            "last_sale_date": "2026-06-01",
        },
    })
    item = ctx["item"]
    assert item["lifetime_revenue_cents"] == item["lifetime_units_sold"] * item["price_cents"]
    assert item["lifetime_revenue_dollars"] == round(item["lifetime_revenue_cents"] / 100, 2)
    assert item["first_sale_date"].startswith("2024-")


def test_sales_series_json_masks_dates_and_units():
    ctx = scrub_template_context({
        "item": {"item_id": "X1", "name": "Cookie"},
        "sales_series_json": '[{"date": "2026-06-01", "units_sold": 6}]',
    })
    import json

    series = json.loads(ctx["sales_series_json"])
    assert series[0]["date"].startswith("2024-")
    assert series[0]["units_sold"] > 0


def test_margin_derived_from_price_and_cost():
    row = {
        "item_id": "P1",
        "units_sold": 10,
        "price_cents": 200,
        "cost_cents": 120,
        "revenue_cents": 2000,
        "gross_profit_cents": 800,
        "margin_pct": 40.0,
    }
    out = scrub_payload([row])[0]
    revenue = out["units_sold"] * out["price_cents"]
    cost_total = out["units_sold"] * out["cost_cents"]
    profit = revenue - cost_total
    assert out["revenue_cents"] == revenue
    assert out["gross_profit_cents"] == profit
    assert out["margin_pct"] == round(profit / revenue * 100, 1)
