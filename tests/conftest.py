"""
Pytest fixtures — isolated, reversible, no live Clover.

- Each ``app`` fixture uses a tempfile SQLite DB (deleted after the test).
- Never uses ``analytics.db`` or ``.env`` writes. See docs/TESTING_STANDARDS.md.
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock

import app.database as db_module
from app.factory import create_app
from app.config import TestConfig
from app.database import init_db

# Paths tests must never use as DB_PATH (developer production DB).
_FORBIDDEN_TEST_DB = frozenset({"analytics.db", "./analytics.db"})


@pytest.fixture
def test_config():
    return TestConfig()


@pytest.fixture
def tmp_db_path():
    """Isolated SQLite file; removed after the test (reversible)."""
    fd, path = tempfile.mkstemp(prefix="mmr_test_", suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _assert_safe_db_path(path: str) -> None:
    normalized = os.path.normpath(path).replace("\\", "/")
    base = os.path.basename(normalized)
    if base in _FORBIDDEN_TEST_DB or normalized.endswith("/analytics.db"):
        raise RuntimeError(
            f"Refusing to run tests against production DB path: {path!r}. "
            "Use the tmp_db_path fixture. See docs/TESTING_STANDARDS.md."
        )


@pytest.fixture
def app(tmp_db_path):
    _assert_safe_db_path(tmp_db_path)
    cfg = TestConfig()
    object.__setattr__(cfg, "DB_PATH", tmp_db_path)
    object.__setattr__(cfg, "SECRET_KEY", "test-secret")
    db_module._db_path = tmp_db_path
    init_db(tmp_db_path)
    application = create_app(config=cfg)
    application.config["TESTING"] = True
    yield application

@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_clover_client():
    return MagicMock()


@pytest.fixture
def sample_items():
    return [
        {
            "id": "item-001",
            "name": "Bottled Water",
            "price": 150,
            "defaultCost": 50,
            "hidden": False,
            "isRevenue": True,
            "itemStock": {"quantity": 100},
            "customer_id": "cust-abc",
            "employee_id": "emp-xyz",
        },
        {
            "id": "item-002",
            "name": "Candy Bar",
            "price": 200,
            "defaultCost": 180,
            "hidden": False,
            "isRevenue": True,
            "itemStock": {"quantity": 50},
        },
        {
            "id": "item-003",
            "name": "Granola",
            "price": 300,
            "defaultCost": 350,
            "hidden": False,
            "isRevenue": True,
            "itemStock": None,
        },
        {
            "id": "item-004",
            "name": "No Cost Item",
            "price": 100,
            "hidden": False,
            "isRevenue": True,
        },
    ]


@pytest.fixture
def sample_line_items():
    return [
        {
            "id": "li-001",
            "item": {"id": "item-001", "name": "Bottled Water"},
            "quantity": 3,
            "price": 150,
            "createdTime": 1746576000000,
            "customer": {"id": "cust-abc", "name": "John Doe"},
            "employee": {"id": "emp-xyz", "name": "Staff Member"},
        },
        {
            "id": "li-002",
            "item": {"id": "item-002", "name": "Candy Bar"},
            "quantity": 1,
            "price": 200,
            "createdTime": 1746576000000,
        },
        {
            "id": "li-003",
            "item": {"id": "item-001", "name": "Bottled Water"},
            "quantity": 2,
            "price": 150,
            "createdTime": 1746576000000,
        },
    ]


@pytest.fixture
def sample_payments():
    return [
        {
            "id": "pay-001",
            "amount": 450,
            "result": "SUCCESS",
            "tender": {"label": "Credit Card", "labelKey": "Credit"},
            "cardTransaction": {"last4": "1234", "cardType": "VISA"},
        },
        {
            "id": "pay-002",
            "amount": 200,
            "result": "SUCCESS",
        },
        {
            "id": "pay-003",
            "amount": 100,
            "result": "FAIL",
        },
    ]
