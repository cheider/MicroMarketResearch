"""
Tests for the privacy enforcement layer (app/etl/transform.py).

These tests are the highest priority in the suite because transform.py
is the only barrier between raw Clover API responses and the database.
"""

import pytest
from app.etl.transform import (
    clean_item,
    clean_stock,
    aggregate_line_items,
    aggregate_payments,
    ITEM_SAFE_FIELDS,
    LINE_ITEM_SAFE_FIELDS,
    STOCK_SAFE_FIELDS,
)

PII_FIELDS = {
    "customer", "customer_id", "customer_name", "email",
    "employee", "employee_id", "card", "last4", "card_type",
    "tender", "card_brand", "cardTransaction",
}


class TestCleanItem:
    def test_returns_required_keys(self, sample_items):
        result = clean_item(sample_items[0])
        assert "item_id" in result
        assert "name" in result
        assert "price_cents" in result

    def test_maps_price_correctly(self, sample_items):
        result = clean_item(sample_items[0])
        assert result["price_cents"] == 150

    def test_maps_cost_correctly(self, sample_items):
        result = clean_item(sample_items[0])
        assert result["cost_cents"] == 50

    def test_maps_clover_cost_field(self):
        raw = {"id": "x", "name": "Chips", "price": 175, "cost": 90}
        result = clean_item(raw)
        assert result["cost_cents"] == 90

    def test_prefers_cost_over_legacy_default_cost(self):
        raw = {"id": "x", "name": "Chips", "price": 175, "cost": 90, "defaultCost": 50}
        result = clean_item(raw)
        assert result["cost_cents"] == 90

    def test_falls_back_to_default_cost(self):
        raw = {"id": "x", "name": "Chips", "price": 175, "defaultCost": 50}
        result = clean_item(raw)
        assert result["cost_cents"] == 50

    def test_null_cost_when_missing(self, sample_items):
        result = clean_item(sample_items[3])
        assert result["cost_cents"] is None

    def test_drops_pii_fields(self, sample_items):
        result = clean_item(sample_items[0])
        for field in PII_FIELDS:
            assert field not in result, f"PII field '{field}' found in cleaned item"

    def test_is_active_when_not_hidden(self, sample_items):
        result = clean_item(sample_items[0])
        assert result["is_active"] == 1

    def test_inactive_when_hidden(self):
        raw = {"id": "x", "name": "Hidden", "price": 100, "hidden": True}
        result = clean_item(raw)
        assert result["is_active"] == 0

    def test_stock_quantity_extracted(self, sample_items):
        result = clean_item(sample_items[0])
        assert result["stock_quantity"] == 100

    def test_stock_quantity_none_when_itemstock_none(self, sample_items):
        result = clean_item(sample_items[2])
        assert result["stock_quantity"] is None

    def test_no_unknown_fields_pass_through(self, sample_items):
        raw = dict(sample_items[0])
        raw["secret_field"] = "should_not_appear"
        result = clean_item(raw)
        assert "secret_field" not in result


class TestCleanStock:
    def test_extracts_item_id_and_quantity(self):
        raw = {"item": {"id": "item-001"}, "quantity": 42}
        result = clean_stock(raw)
        assert result["item_id"] == "item-001"
        assert result["quantity"] == 42

    def test_falls_back_to_stockcount(self):
        raw = {"item": {"id": "item-002"}, "stockCount": 10}
        result = clean_stock(raw)
        assert result["quantity"] == 10

    def test_returns_zero_when_no_quantity(self):
        raw = {"item": {"id": "item-003"}}
        result = clean_stock(raw)
        assert result["quantity"] == 0

    def test_no_pii_in_result(self):
        raw = {"item": {"id": "item-001", "name": "Water"}, "quantity": 5, "employee_id": "emp-1"}
        result = clean_stock(raw)
        for field in PII_FIELDS:
            assert field not in result


class TestAggregateLineItems:
    def test_aggregates_same_item_same_day(self, sample_line_items):
        result = aggregate_line_items(sample_line_items)
        key = ("item-001", "2025-05-07")
        assert key in result
        assert result[key]["units_sold"] == 5

    def test_correct_revenue_aggregation(self, sample_line_items):
        result = aggregate_line_items(sample_line_items)
        key = ("item-001", "2025-05-07")
        assert result[key]["gross_revenue_cents"] == 5 * 150

    def test_different_items_separate_keys(self, sample_line_items):
        result = aggregate_line_items(sample_line_items)
        assert any("item-001" in str(k) for k in result)
        assert any("item-002" in str(k) for k in result)

    def test_no_pii_in_result(self, sample_line_items):
        result = aggregate_line_items(sample_line_items)
        for row in result.values():
            for field in PII_FIELDS:
                assert field not in row

    def test_skips_line_items_without_item_ref(self):
        raw = [{"id": "li-x", "quantity": 2, "price": 100, "createdTime": 1746576000000}]
        result = aggregate_line_items(raw)
        assert len(result) == 0

    def test_skips_line_items_without_timestamp(self):
        raw = [{"id": "li-y", "item": {"id": "item-001"}, "quantity": 1, "price": 100}]
        result = aggregate_line_items(raw)
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        result = aggregate_line_items([])
        assert result == {}


class TestAggregatePayments:
    def test_sums_successful_payments_only(self, sample_payments):
        result = aggregate_payments(sample_payments)
        assert result["total_revenue_cents"] == 650

    def test_no_card_data_in_result(self, sample_payments):
        result = aggregate_payments(sample_payments)
        for field in PII_FIELDS:
            assert field not in result

    def test_empty_input(self):
        result = aggregate_payments([])
        assert result["total_revenue_cents"] == 0
