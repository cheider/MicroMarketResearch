"""Missing cost export for Clover defaultCost remediation."""

from datetime import date

import app.analysis.periods as periods
from app.database import get_connection, init_db
from app.analysis.cost_collection import (
    get_missing_cost_items,
    missing_cost_dataframe,
    MISSING_COST_CSV_COLUMNS,
)


def test_missing_cost_items_sorted_by_sales(app):
    init_db(app.config["DB_PATH"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, cost_cents, is_active, last_synced)
            VALUES
                ('A', 'High Seller', 200, NULL, 1, '2026-01-01'),
                ('B', 'Low Seller', 150, NULL, 1, '2026-01-01'),
                ('C', 'Has Cost', 100, 50, 1, '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES
                ('A', '2026-05-20', 10, 2000),
                ('B', '2026-05-20', 1, 150)
            """
        )

    rows = get_missing_cost_items(sales_period="90d")
    assert len(rows) == 2
    assert rows[0]["item_id"] == "A"
    assert rows[1]["item_id"] == "B"


def test_missing_cost_csv_has_fill_in_columns(app):
    init_db(app.config["DB_PATH"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, cost_cents, is_active, last_synced)
            VALUES ('X', 'Snack', 125, NULL, 1, '2026-01-01')
            """
        )

    df = missing_cost_dataframe()
    assert list(df.columns) == MISSING_COST_CSV_COLUMNS
    assert df.iloc[0]["item_id"] == "X"
    assert df.iloc[0]["cost_dollars_to_enter"] == ""
    assert df.iloc[0]["notes"] == ""


def test_missing_cost_download_route(client, monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: date(2026, 5, 24))
    response = client.get(
        "/tools/inventory/missing-costs/download",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b"cost_dollars_to_enter" in response.data
    assert b"item_id" in response.data


def test_legacy_missing_cost_download_redirects(client, monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: date(2026, 5, 24))
    response = client.get(
        "/dashboards/profit/missing-costs/download",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"cost_dollars_to_enter" in response.data


def test_profit_dashboard_links_missing_cost_tools(client, monkeypatch):
    monkeypatch.setattr(periods, "today", lambda: date(2026, 5, 24))
    response = client.get("/dashboards/profit")
    assert response.status_code == 200
    assert b"/tools/inventory/missing-costs" in response.data
