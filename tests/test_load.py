import pytest
import app.database as db_module
from app.database import get_connection
from app.etl.load import upsert_fetched_orders, get_fetched_order_ids


@pytest.fixture(autouse=True)
def setup_db(app):
    db_module._db_path = app.config["DB_PATH"]
    yield


class TestFetchedOrdersLoad:
    def test_get_fetched_order_ids_empty_on_fresh_db(self, app):
        ids = get_fetched_order_ids()
        assert ids == set()

    def test_upsert_stores_order_ids(self, app):
        upsert_fetched_orders(["order-1", "order-2", "order-3"])
        ids = get_fetched_order_ids()
        assert ids == {"order-1", "order-2", "order-3"}

    def test_upsert_is_idempotent(self, app):
        upsert_fetched_orders(["order-abc"])
        upsert_fetched_orders(["order-abc"])  # second call must not raise
        ids = get_fetched_order_ids()
        assert ids == {"order-abc"}

    def test_upsert_empty_list_is_no_op(self, app):
        upsert_fetched_orders([])  # must not raise
        ids = get_fetched_order_ids()
        assert ids == set()

    def test_upsert_accumulates_across_calls(self, app):
        upsert_fetched_orders(["order-1"])
        upsert_fetched_orders(["order-2"])
        ids = get_fetched_order_ids()
        assert ids == {"order-1", "order-2"}

    def test_get_returns_set_type(self, app):
        upsert_fetched_orders(["order-x"])
        ids = get_fetched_order_ids()
        assert isinstance(ids, set)


class TestUpsertItemsCost:
    def test_preserves_existing_cost_when_sync_payload_omits_cost(self, app):
        from app.etl.load import upsert_items

        upsert_items([{
            "item_id": "item-1",
            "name": "Water",
            "price_cents": 150,
            "cost_cents": 55,
            "is_active": 1,
            "category_id": None,
        }])
        upsert_items([{
            "item_id": "item-1",
            "name": "Water",
            "price_cents": 150,
            "cost_cents": None,
            "is_active": 1,
            "category_id": None,
        }])

        with get_connection() as conn:
            row = conn.execute(
                "SELECT cost_cents FROM items WHERE item_id = 'item-1'"
            ).fetchone()
        assert row["cost_cents"] == 55

    def test_updates_cost_when_sync_payload_includes_cost(self, app):
        from app.etl.load import upsert_items

        upsert_items([{
            "item_id": "item-2",
            "name": "Bar",
            "price_cents": 200,
            "cost_cents": 80,
            "is_active": 1,
            "category_id": None,
        }])
        upsert_items([{
            "item_id": "item-2",
            "name": "Bar",
            "price_cents": 200,
            "cost_cents": 95,
            "is_active": 1,
            "category_id": None,
        }])

        with get_connection() as conn:
            row = conn.execute(
                "SELECT cost_cents FROM items WHERE item_id = 'item-2'"
            ).fetchone()
        assert row["cost_cents"] == 95
