import pytest
import app.database as db_module
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
