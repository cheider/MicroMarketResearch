"""Unit tests for app/analysis/quarter_analytics.py"""

import pytest
from datetime import date, timedelta

import app.database as db_module
from app.database import get_connection, init_db
from app.analysis.quarter_analytics import (
    create_quarter,
    delete_quarter,
    get_all_quarters,
    get_quarter_by_id,
    get_quarter_weekly_revenue,
    compare_quarters,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_db_path):
    """Point the module at a fresh temp DB for every test."""
    db_module._db_path = tmp_db_path
    init_db(tmp_db_path)
    yield


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_create_quarter_stores_correctly():
    qid = create_quarter("2024-2025", "Fall", "2024-08-26", "2024-11-22")
    q = get_quarter_by_id(qid)
    assert q is not None
    assert q["school_year"] == "2024-2025"
    assert q["season"] == "Fall"
    assert q["start_date"] == "2024-08-26"
    assert q["end_date"] == "2024-11-22"
    assert q["total_weeks"] > 0
    assert q["label"] == "Fall 2024-2025"


def test_get_all_quarters_returns_list():
    create_quarter("2024-2025", "Fall",   "2024-08-26", "2024-11-22")
    create_quarter("2024-2025", "Spring", "2025-02-17", "2025-05-23")
    quarters = get_all_quarters()
    assert len(quarters) == 2
    seasons = [q["season"] for q in quarters]
    assert "Fall" in seasons
    assert "Spring" in seasons


def test_create_quarter_duplicate_raises():
    create_quarter("2024-2025", "Fall", "2024-08-26", "2024-11-22")
    with pytest.raises(ValueError, match="already exists"):
        create_quarter("2024-2025", "Fall", "2024-08-26", "2024-11-22")


def test_create_quarter_invalid_season_raises():
    with pytest.raises(ValueError, match="season must be one of"):
        create_quarter("2024-2025", "Autumn", "2024-08-26", "2024-11-22")


def test_create_quarter_end_before_start_raises():
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        create_quarter("2024-2025", "Fall", "2024-11-22", "2024-08-26")


def test_create_quarter_same_start_end_raises():
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        create_quarter("2024-2025", "Fall", "2024-08-26", "2024-08-26")


def test_delete_quarter_removes_row():
    qid = create_quarter("2024-2025", "Fall", "2024-08-26", "2024-11-22")
    delete_quarter(qid)
    assert get_quarter_by_id(qid) is None
    assert get_all_quarters() == []


def test_get_quarter_by_id_missing_returns_none():
    result = get_quarter_by_id(9999)
    assert result is None


# ---------------------------------------------------------------------------
# Weekly revenue tests
# ---------------------------------------------------------------------------

def _seed_item_and_sales(start_date_str: str, num_days: int):
    """Insert a minimal item and `num_days` days of sales from start_date."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO items (item_id, name, price_cents, cost_cents,"
            " is_active, last_synced) VALUES (?,?,?,?,?,?)",
            ("item-test", "Test Item", 200, 100, 1, "2024-01-01"),
        )
        start = date.fromisoformat(start_date_str)
        for i in range(num_days):
            d = (start + timedelta(days=i)).isoformat()
            conn.execute(
                "INSERT INTO daily_sales"
                " (item_id, sale_date, units_sold, gross_revenue_cents)"
                " VALUES (?,?,?,?)",
                ("item-test", d, 2, 400),
            )


def test_get_quarter_weekly_revenue_empty_db():
    qid = create_quarter("2024-2025", "Fall", "2024-08-26", "2024-09-08")
    weeks = get_quarter_weekly_revenue(qid)
    assert len(weeks) == 2
    for w in weeks:
        assert w["revenue_cents"] == 0
        assert w["units_sold"] == 0
        assert w["profit_cents"] == 0


def test_get_quarter_weekly_revenue_with_data():
    # Quarter spans 2 weeks: days 0-6 = week 1, days 7-13 = week 2
    start = "2024-08-26"
    end = "2024-09-08"
    qid = create_quarter("2024-2025", "Fall", start, end)
    _seed_item_and_sales(start, 14)  # 14 days of sales

    weeks = get_quarter_weekly_revenue(qid)
    assert len(weeks) == 2

    w1 = next(w for w in weeks if w["week_num"] == 1)
    w2 = next(w for w in weeks if w["week_num"] == 2)

    # 7 days × 2 units × 400 cents = 5600 per week revenue
    assert w1["revenue_cents"] == 7 * 400
    assert w2["revenue_cents"] == 7 * 400
    # Profit = (price - cost) × units = (200-100) × 2 × 7 = 1400
    assert w1["profit_cents"] == 7 * 2 * 100
    assert w2["profit_cents"] == 7 * 2 * 100


def test_get_quarter_weekly_revenue_nonexistent_quarter():
    result = get_quarter_weekly_revenue(9999)
    assert result == []


# ---------------------------------------------------------------------------
# compare_quarters tests
# ---------------------------------------------------------------------------

def _seed_item(item_id="item-a", price=200, cost=100):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO items"
            " (item_id, name, price_cents, cost_cents, is_active, last_synced)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, "Item", price, cost, 1, "2024-01-01"),
        )


def _seed_sales(item_id, start_date_str, num_days, units=2, revenue=400):
    start = date.fromisoformat(start_date_str)
    with get_connection() as conn:
        for i in range(num_days):
            d = (start + timedelta(days=i)).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO daily_sales"
                " (item_id, sale_date, units_sold, gross_revenue_cents)"
                " VALUES (?,?,?,?)",
                (item_id, d, units, revenue),
            )


def test_compare_quarters_aligned_weeks():
    _seed_item()
    q1_id = create_quarter(
        "2024-2025", "Fall", "2024-08-26", "2024-09-08"
    )
    q2_id = create_quarter(
        "2024-2025", "Spring", "2025-02-17", "2025-03-02"
    )
    _seed_sales("item-a", "2024-08-26", 14, units=2, revenue=400)
    _seed_sales("item-a", "2025-02-17", 14, units=3, revenue=600)

    result = compare_quarters(q1_id, q2_id)
    assert result["q1"]["season"] == "Fall"
    assert result["q2"]["season"] == "Spring"
    assert len(result["weeks"]) == 2

    w1 = result["weeks"][0]
    assert w1["week_num"] == 1
    assert w1["q1_revenue"] == 7 * 400
    assert w1["q2_revenue"] == 7 * 600
    assert w1["revenue_delta"] == 7 * 600 - 7 * 400


def test_compare_quarters_different_lengths():
    _seed_item()
    # q1 = 2 weeks, q2 = 1 week
    q1_id = create_quarter(
        "2024-2025", "Fall", "2024-08-26", "2024-09-08"
    )
    q2_id = create_quarter(
        "2024-2025", "Spring", "2025-02-17", "2025-02-23"
    )
    _seed_sales("item-a", "2024-08-26", 14, units=2, revenue=400)
    _seed_sales("item-a", "2025-02-17", 7, units=2, revenue=400)

    result = compare_quarters(q1_id, q2_id)
    # Should have 2 rows; week 2 q2 values should be 0
    assert len(result["weeks"]) == 2
    w2 = result["weeks"][1]
    assert w2["week_num"] == 2
    assert w2["q2_revenue"] == 0
    assert w2["q1_revenue"] == 7 * 400


def test_compare_quarters_missing_quarter():
    q1_id = create_quarter(
        "2024-2025", "Fall", "2024-08-26", "2024-09-08"
    )
    result = compare_quarters(q1_id, 9999)
    assert result["q2"] is None
    assert result["weeks"] == []
