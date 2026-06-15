"""Inventory Tools: CSV, board API, item profile, manual enrichment guard."""

import io

from app.database import get_connection, init_db
from app.analysis.item_context import get_item_profile, infer_supplier
from app.etl.product_taxonomy import derive_item_product_categories, seed_product_categories
from app.inventory_tools.categorization_io import (
    export_categorization_csv,
    import_categorization_csv,
)
from app.inventory_tools.categorization_service import (
    apply_stored_suggestions,
    get_category_board_state,
)
from app.etl.category_suggestions import suggest_product_category_slug


def _seed_item(
    conn,
    item_id: str,
    name: str,
    *,
    product_category_id=None,
    product_category_source=None,
    price_cents=100,
):
    conn.execute(
        """
        INSERT INTO items
            (item_id, name, price_cents, is_active, last_synced,
             product_category_id, product_category_source)
        VALUES (?, ?, ?, 1, '2026-01-01', ?, ?)
        """,
        (item_id, name, price_cents, product_category_id, product_category_source),
    )


def test_product_categories_seeded_with_colors(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT color_hex, sort_order FROM product_categories WHERE product_category_id='drinks'"
        ).fetchone()
    assert row["color_hex"] == "#4f8ef7"
    assert row["sort_order"] == 1


def test_csv_round_trip_preserves_manual(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        _seed_item(conn, "A1", "Chips", product_category_id="snacks", product_category_source="manual")
        _seed_item(conn, "A2", "Latte", price_cents=0)

    csv_before = export_categorization_csv()
    summary = import_categorization_csv(io.StringIO(csv_before))
    assert summary["updated"] >= 2
    assert not summary["errors"]

    with get_connection() as conn:
        row = conn.execute(
            "SELECT product_category_id, product_category_source FROM items WHERE item_id='A1'"
        ).fetchone()
    assert row["product_category_id"] == "snacks"
    assert row["product_category_source"] == "manual"


def test_import_leaves_items_not_in_csv_unchanged(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        _seed_item(conn, "KEEP", "Granola", product_category_id="snacks", product_category_source="manual")
        _seed_item(conn, "OTHER", "Water")

    partial = "item_id,item_name,product_category_id\nOTHER,Water,drinks\n"
    summary = import_categorization_csv(io.StringIO(partial))
    assert summary["not_in_csv_unchanged"] == 1
    assert "KEEP" in summary["not_in_csv_item_ids"]

    with get_connection() as conn:
        keep = conn.execute(
            "SELECT product_category_id FROM items WHERE item_id='KEEP'"
        ).fetchone()
        other = conn.execute(
            "SELECT product_category_id, product_category_source FROM items WHERE item_id='OTHER'"
        ).fetchone()
    assert keep["product_category_id"] == "snacks"
    assert other["product_category_id"] == "drinks"
    assert other["product_category_source"] == "manual"


def test_import_invalid_slug_returns_errors(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        _seed_item(conn, "X1", "Test")

    bad = "item_id,item_name,product_category_id\nX1,Test,not_a_real_slug\n"
    summary = import_categorization_csv(io.StringIO(bad))
    assert summary["errors"]
    with get_connection() as conn:
        row = conn.execute(
            "SELECT product_category_id FROM items WHERE item_id='X1'"
        ).fetchone()
    assert row["product_category_id"] is None


def test_manual_item_skipped_by_derive_after_sync(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO categories (category_id, name, kind, last_synced)
            VALUES ('CAT1', 'Drinks', 'product', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, category_id, is_active, last_synced,
                 product_category_id, product_category_source)
            VALUES ('M1', 'Manual Latte', 500, 'CAT1', 1, '2026-01-01', 'snacks', 'manual')
            """
        )

    derive_item_product_categories()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT product_category_id, product_category_source FROM items WHERE item_id='M1'"
        ).fetchone()
    assert row["product_category_id"] == "snacks"
    assert row["product_category_source"] == "manual"


def test_get_item_profile_lifetime_totals(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        _seed_item(conn, "P1", "Bottled Water", product_category_id="drinks")
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('P1', '2026-01-01', 2, 400), ('P1', '2026-02-01', 3, 600)
            """
        )
        conn.execute(
            """
            INSERT INTO stock_snapshots (item_id, snapshot_ts, quantity)
            VALUES ('P1', '2026-06-01T12:00:00', 12)
            """
        )

    profile = get_item_profile("P1")
    assert profile is not None
    assert profile["lifetime_units_sold"] == 5
    assert profile["lifetime_revenue_cents"] == 1000
    assert profile["first_sale_date"] == "2026-01-01"
    assert profile["on_hand_qty"] == 12


def test_board_api_returns_grouped_columns(client, app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        _seed_item(conn, "B1", "Cookie", product_category_id="snacks", product_category_source="manual")

    response = client.get("/api/inventory-tools/board")
    assert response.status_code == 200
    data = response.get_json()
    assert "columns" in data
    assert any(c["product_category_id"] == "snacks" for c in data["columns"])
    snacks_col = next(c for c in data["columns"] if c["product_category_id"] == "snacks")
    assert any(i["item_id"] == "B1" for i in snacks_col["chips"])


def test_inventory_tools_routes_return_200(client):
    for path in (
        "/tools/inventory",
        "/tools/inventory/categories",
        "/tools/inventory/missing-costs",
    ):
        assert client.get(path).status_code == 200


def test_legacy_missing_cost_download_redirects(client):
    response = client.get("/dashboards/profit/missing-costs/download")
    assert response.status_code in (302, 308)
    assert "/tools/inventory/missing-costs/download" in response.location


def test_suggest_school_supplies_and_modifiers():
    assert suggest_product_category_slug("Notebook 5x8") == "school_supplies"
    assert suggest_product_category_slug("Vanilla Flavor", price_cents=0) == "modifiers"


def test_apply_stored_suggestions_promotes_unassigned(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced,
                 suggested_product_category_id)
            VALUES ('SUG1', 'Turkey Sandwich', 650, 1, '2026-01-01', 'sandwiches')
            """
        )

    result = apply_stored_suggestions()
    assert result["updated"] == 1
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT product_category_id, product_category_source,
                   suggested_product_category_id
            FROM items WHERE item_id='SUG1'
            """
        ).fetchone()
    assert row["product_category_id"] == "sandwiches"
    assert row["product_category_source"] == "manual"
    assert row["suggested_product_category_id"] is None


def test_suggest_sandwich_and_soup():
    assert suggest_product_category_slug("Turkey Sandwich") == "sandwiches"
    assert suggest_product_category_slug("Tomato Soup 12oz") == "soup"


def test_product_categories_include_sandwiches_and_soup(app):
    init_db(app.config["DB_PATH"])
    seed_product_categories()
    with get_connection() as conn:
        slugs = {
            r["product_category_id"]
            for r in conn.execute("SELECT product_category_id FROM product_categories").fetchall()
        }
    assert "sandwiches" in slugs
    assert "soup" in slugs


def test_infer_supplier_from_name():
    assert infer_supplier(None, "Cheetos Crunchy") == "Snak Club"
