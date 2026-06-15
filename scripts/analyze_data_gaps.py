"""One-off data gap analysis for analytics.db (read-only)."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "analytics.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row


def one(sql, **params):
    return conn.execute(sql, params).fetchone()


def many(sql, **params):
    return conn.execute(sql, params).fetchall()


def section(title):
    print(f"\n=== {title} ===")


section("COUNTS")
for t in ("items", "categories", "daily_sales", "quarters", "stock_snapshots"):
    print(f"  {t}: {one(f'SELECT COUNT(*) c FROM {t}')['c']}")

active = one("SELECT COUNT(*) c FROM items WHERE is_active=1")["c"]
inactive = one("SELECT COUNT(*) c FROM items WHERE is_active=0")["c"]
print(f"  active items: {active}, inactive/hidden: {inactive}")

section("PRICING GAPS")
no_price = one(
    "SELECT COUNT(*) c FROM items WHERE is_active=1 AND (price_cents IS NULL OR price_cents<=0)"
)["c"]
no_cost = one("SELECT COUNT(*) c FROM items WHERE is_active=1 AND cost_cents IS NULL")["c"]
print(f"  missing/zero price (active): {no_price}")
print(f"  missing cost (active): {no_cost}")

section("Top sellers with missing price")
for r in many(
    """
    SELECT i.name, i.price_cents, SUM(ds.units_sold) units, SUM(ds.gross_revenue_cents) rev
    FROM items i JOIN daily_sales ds ON i.item_id=ds.item_id
    WHERE i.is_active=1 AND (i.price_cents IS NULL OR i.price_cents<=0)
    GROUP BY i.item_id ORDER BY units DESC LIMIT 15
    """
):
    print(f"  {r['units']:4d} units | ${r['rev']/100:8.2f} | {r['name'][:50]}")

section("CATEGORY GAPS")
no_cat = one(
    "SELECT COUNT(*) c FROM items WHERE is_active=1 AND (category_id IS NULL OR category_id='')"
)["c"]
print(f"  uncategorized (active): {no_cat}")

section("Items per category")
for r in many(
    """
    SELECT COALESCE(c.name, '(uncategorized)') cat, COUNT(*) n
    FROM items i LEFT JOIN categories c ON i.category_id=c.category_id
    WHERE i.is_active=1 GROUP BY cat ORDER BY n DESC
    """
):
    print(f"  {r['n']:4d}  {r['cat']}")

section("Sample uncategorized items (up to 25)")
for r in many(
    """
    SELECT i.name, i.price_cents, i.cost_cents,
           COALESCE(SUM(ds.units_sold),0) units
    FROM items i
    LEFT JOIN daily_sales ds ON i.item_id=ds.item_id
    WHERE i.is_active=1 AND (i.category_id IS NULL OR i.category_id='')
    GROUP BY i.item_id ORDER BY units DESC, i.name LIMIT 25
    """
):
    p = r["price_cents"] / 100 if r["price_cents"] else 0
    print(f"  {r['units']:4d} units | ${p:5.2f} | {r['name'][:55]}")

section("Categories in Clover DB")
for r in many("SELECT category_id, name FROM categories ORDER BY name"):
    print(f"  {r['name']}")

section("Margin blind spots (has sales, no cost)")
for r in many(
    """
    SELECT i.name, i.price_cents, SUM(ds.units_sold) units
    FROM items i JOIN daily_sales ds ON i.item_id=ds.item_id
    WHERE i.is_active=1 AND i.cost_cents IS NULL AND i.price_cents>0
    GROUP BY i.item_id ORDER BY units DESC LIMIT 15
    """
):
    print(f"  {r['units']:4d} units | ${r['price_cents']/100:.2f} | {r['name'][:50]}")

section("Duplicate-ish names (possible cleanup)")
for r in many(
    """
    SELECT LOWER(TRIM(name)) n, COUNT(*) c FROM items WHERE is_active=1
    GROUP BY LOWER(TRIM(name)) HAVING c>1 ORDER BY c DESC LIMIT 10
    """
):
    print(f"  {r['c']}x  {r['n'][:60]}")

section("Sales revenue coverage")
total_rev = one("SELECT SUM(gross_revenue_cents) r FROM daily_sales")["r"] or 0
zero_price_rev = one(
    """
    SELECT SUM(ds.gross_revenue_cents) r
    FROM daily_sales ds JOIN items i ON ds.item_id=i.item_id
    WHERE i.price_cents IS NULL OR i.price_cents<=0
    """
)["r"] or 0
print(f"  total gross revenue in DB: ${total_rev/100:,.2f}")
print(f"  revenue tied to zero-price items: ${zero_price_rev/100:,.2f}")

conn.close()
