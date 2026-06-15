"""Category analysis page routes and product-type rollups."""

from app.analysis.category_analysis import get_category_analysis_report
from app.database import get_connection, init_db
from app.etl.product_taxonomy import seed_product_categories


def test_category_analysis_page_returns_200(client, app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    response = client.get("/analysis/categories")
    assert response.status_code == 200
    assert b"Category Analysis" in response.data
    assert b"Sales by product type" in response.data
    assert b"Clover tag" not in response.data


def test_category_analysis_with_sales_data(client, app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced, product_category_id)
            VALUES ('GUM1', 'Extra Gum', 125, 1, '2026-01-01', 'snacks')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('GUM1', '2026-06-01', 10, 1250)
            """
        )

    response = client.get("/analysis/categories?period=90d")
    assert response.status_code == 200
    assert b"Snacks" in response.data


def test_category_analysis_uses_product_type_not_clover_supplier_tag(client, app):
    """Raw Clover supplier tags must not drive product-type sales buckets."""
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO categories (category_id, name, kind, last_synced)
            VALUES ('SUP1', 'US Foods', 'supplier', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced,
                 category_id, product_category_id, product_category_source)
            VALUES ('CHIP1', 'Potato Chips', 150, 1, '2026-01-01',
                    'SUP1', 'snacks', 'manual')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('CHIP1', '2026-06-01', 4, 600)
            """
        )

    report = get_category_analysis_report(period="90d")
    names = [row["name"] for row in report["by_product"]]
    assert "Snacks" in names
    assert "US Foods" not in names

    response = client.get("/analysis/categories?period=90d")
    assert response.status_code == 200
    assert b"Snacks" in response.data
    assert b"US Foods" not in response.data


def test_category_analysis_includes_suggested_product_types(client, app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced,
                 suggested_product_category_id)
            VALUES ('LATTE', 'Latte', 350, 1, '2026-01-01', 'drinks')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('LATTE', '2026-06-01', 3, 1050)
            """
        )

    report = get_category_analysis_report(period="90d")
    names = [row["name"] for row in report["by_product"]]
    assert "Drinks (suggested)" in names

    response = client.get("/analysis/categories?period=90d")
    assert response.status_code == 200
    assert b"Drinks (suggested)" in response.data


def test_demo_mode_masks_ids_on_category_page(client, app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    client.set_cookie("mmr_demo_anonymize", "1")
    response = client.get("/analysis/categories")
    assert response.status_code == 200
    assert b"Demo mode" in response.data
