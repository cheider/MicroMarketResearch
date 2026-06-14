"""Route/integration tests for the quarters blueprint."""

import pytest
from datetime import date, timedelta

import app.database as db_module
from app.database import get_connection, init_db
from app.analysis.quarter_analytics import create_quarter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_item_and_sales(start_date_str: str, num_days: int):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO items"
            " (item_id, name, price_cents, cost_cents,"
            "  is_active, last_synced)"
            " VALUES (?,?,?,?,?,?)",
            ("item-route", "Route Item", 200, 100, 1, "2024-01-01"),
        )
        start = date.fromisoformat(start_date_str)
        for i in range(num_days):
            d = (start + timedelta(days=i)).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO daily_sales"
                " (item_id, sale_date, units_sold, gross_revenue_cents)"
                " VALUES (?,?,?,?)",
                ("item-route", d, 2, 400),
            )


# ---------------------------------------------------------------------------
# Management page
# ---------------------------------------------------------------------------

def test_manage_quarters_get_empty(client):
    resp = client.get("/analysis/quarters/manage")
    assert resp.status_code == 200
    assert b"Manage Quarters" in resp.data
    assert b"No quarters defined yet" in resp.data


def test_create_quarter_via_post(client):
    resp = client.post(
        "/analysis/quarters/manage",
        data={
            "school_year": "2024-2025",
            "season": "Fall",
            "start_date": "2024-08-26",
            "end_date": "2024-11-22",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    assert b"Fall" in resp.data
    assert b"2024-2025" in resp.data


def test_create_quarter_missing_fields_flash(client):
    resp = client.post(
        "/analysis/quarters/manage",
        data={"school_year": "2024-2025"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"All fields are required" in resp.data


def test_create_quarter_bad_dates_flash(client):
    resp = client.post(
        "/analysis/quarters/manage",
        data={
            "school_year": "2024-2025",
            "season": "Fall",
            "start_date": "2024-11-22",
            "end_date": "2024-08-26",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"end_date must be after start_date" in resp.data


def test_create_quarter_duplicate_flash(client):
    client.post(
        "/analysis/quarters/manage",
        data={
            "school_year": "2024-2025",
            "season": "Fall",
            "start_date": "2024-08-26",
            "end_date": "2024-11-22",
        },
    )
    resp = client.post(
        "/analysis/quarters/manage",
        data={
            "school_year": "2024-2025",
            "season": "Fall",
            "start_date": "2024-08-26",
            "end_date": "2024-11-22",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_delete_quarter(client, app):
    with app.app_context():
        qid = create_quarter(
            "2024-2025", "Fall", "2024-08-26", "2024-11-22"
        )
    resp = client.post(
        f"/analysis/quarters/{qid}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    assert b"No quarters defined yet" in resp.data


def test_delete_nonexistent_quarter(client):
    resp = client.post(
        "/analysis/quarters/9999/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data


# ---------------------------------------------------------------------------
# Comparison dashboard
# ---------------------------------------------------------------------------

def test_quarter_comparison_no_quarters(client):
    resp = client.get("/analysis/quarters")
    assert resp.status_code == 200
    assert b"No quarters have been defined" in resp.data


def test_quarter_comparison_no_params(client, app):
    with app.app_context():
        create_quarter("2024-2025", "Fall", "2024-08-26", "2024-09-08")
    resp = client.get("/analysis/quarters")
    assert resp.status_code == 200
    # Selector should be shown
    assert b"Quarter 1" in resp.data


def test_quarter_comparison_missing_one_param(client, app):
    with app.app_context():
        qid = create_quarter(
            "2024-2025", "Fall", "2024-08-26", "2024-09-08"
        )
    resp = client.get(f"/analysis/quarters?q1={qid}")
    assert resp.status_code == 200
    # No chart without both params
    assert b"revenueChart" not in resp.data


def test_quarter_comparison_with_data(client, app):
    with app.app_context():
        q1_id = create_quarter(
            "2024-2025", "Fall", "2024-08-26", "2024-09-08"
        )
        q2_id = create_quarter(
            "2024-2025", "Spring", "2025-02-17", "2025-03-02"
        )
        _seed_item_and_sales("2024-08-26", 14)
        _seed_item_and_sales("2025-02-17", 14)

    resp = client.get(f"/analysis/quarters?q1={q1_id}&q2={q2_id}")
    assert resp.status_code == 200
    assert b"revenueChart" in resp.data
    assert b"profitChart" in resp.data
    assert b"Week 1" in resp.data
    assert b"Week 2" in resp.data


def test_quarter_comparison_shows_kpi_cards(client, app):
    with app.app_context():
        q1_id = create_quarter(
            "2024-2025", "Fall", "2024-08-26", "2024-09-08"
        )
        q2_id = create_quarter(
            "2024-2025", "Spring", "2025-02-17", "2025-03-02"
        )
        _seed_item_and_sales("2024-08-26", 14)
        _seed_item_and_sales("2025-02-17", 14)

    resp = client.get(f"/analysis/quarters?q1={q1_id}&q2={q2_id}")
    assert resp.status_code == 200
    assert b"Total Revenue Delta" in resp.data
    assert b"Best Week" in resp.data
