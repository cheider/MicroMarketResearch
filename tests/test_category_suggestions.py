"""Product category suggestion pipeline and report resolution."""

from app.database import get_connection, init_db
from app.etl.category_suggestions import (
    apply_category_suggestions,
    suggest_product_category_slug,
)
from app.analysis.category_resolution import (
    SUGGESTED_PREFIX,
    parse_category_filter,
    use_suggested_categories,
)
from app.analysis.dashboard_analytics import get_sales_by_category
from app.taxonomy import clover_category_kind


def test_suggest_latte_is_drinks():
    assert suggest_product_category_slug("Latte 12oz") == "drinks"


def test_suggest_red_bull_is_drinks():
    assert suggest_product_category_slug("Red Bull Sugar-Free") == "drinks"


def test_suggest_notebook_is_school_supplies():
    assert suggest_product_category_slug("Spiral Notebook") == "school_supplies"


def test_suggest_sandwich_is_sandwiches_not_prepared_food():
    assert suggest_product_category_slug("Ham Sandwich") == "sandwiches"


def test_suggest_soup_slug():
    assert suggest_product_category_slug("Chicken Noodle Soup") == "soup"


def test_suggest_salad_slug():
    assert suggest_product_category_slug("Garden Salad") == "salad"
    assert suggest_product_category_slug("Chicken Caesar") == "salad"


def test_suggest_zero_price_flavor_is_modifiers():
    assert suggest_product_category_slug("Vanilla Flavor", price_cents=0) == "modifiers"


def test_clover_kind_separates_supplier_and_location():
    assert clover_category_kind("Snak Club") == "supplier"
    assert clover_category_kind("Lily Pad Cafe") == "location"
    assert clover_category_kind("Drinks") == "product"


def test_apply_category_suggestions_writes_local_only(app):
    init_db(app.config["DB_PATH"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced)
            VALUES ('ITEM1', 'Red Bull', 275, 1, '2026-01-01')
            """
        )

    updated = apply_category_suggestions()
    assert updated >= 1

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT category_id, product_category_id, suggested_product_category_id
            FROM items WHERE item_id='ITEM1'
            """
        ).fetchone()
    assert row["category_id"] is None
    assert row["product_category_id"] is None
    assert row["suggested_product_category_id"] == "drinks"


def test_sales_by_category_shows_suggested_bucket(app):
    init_db(app.config["DB_PATH"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO items
                (item_id, name, price_cents, is_active, last_synced,
                 suggested_product_category_id)
            VALUES ('LATTE', 'Latte', 0, 1, '2026-01-01', 'drinks')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_sales (item_id, sale_date, units_sold, gross_revenue_cents)
            VALUES ('LATTE', '2026-06-01', 5, 2500)
            """
        )

    rows = get_sales_by_category(period="90d", use_suggested=True)
    names = [r["name"] for r in rows]
    assert "Drinks (suggested)" in names


def test_parse_suggested_filter():
    parsed, is_suggested = parse_category_filter(f"{SUGGESTED_PREFIX}drinks")
    assert parsed == "drinks"
    assert is_suggested is True


def test_use_suggested_categories_cookie():
    assert use_suggested_categories("1") is True
    assert use_suggested_categories("0") is False
    assert use_suggested_categories(None) is False
