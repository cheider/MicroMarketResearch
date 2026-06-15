import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app.database import get_connection, init_db
from app.etl.category_suggestions import apply_category_suggestions
from app.etl.product_taxonomy import (
    classify_clover_categories,
    derive_item_product_categories,
    seed_product_categories,
)

init_db(Config().DB_PATH)
seed_product_categories()
classify_clover_categories()
derive_item_product_categories()
n = apply_category_suggestions()

with get_connection() as conn:
    official_product = conn.execute(
        """
        SELECT COUNT(*) FROM items
        WHERE is_active = 1
          AND product_category_id IS NOT NULL
          AND product_category_id != ''
        """
    ).fetchone()[0]
    suggested_product = conn.execute(
        """
        SELECT COUNT(*) FROM items
        WHERE is_active = 1
          AND (product_category_id IS NULL OR product_category_id = '')
          AND suggested_product_category_id IS NOT NULL
          AND suggested_product_category_id != ''
        """
    ).fetchone()[0]
    no_product = conn.execute(
        """
        SELECT COUNT(*) FROM items
        WHERE is_active = 1
          AND (product_category_id IS NULL OR product_category_id = '')
          AND (suggested_product_category_id IS NULL
               OR suggested_product_category_id = '')
        """
    ).fetchone()[0]
    by_kind = conn.execute(
        """
        SELECT COALESCE(c.kind, 'unknown') AS kind, COUNT(*) AS n
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.category_id
        WHERE i.is_active = 1
        GROUP BY COALESCE(c.kind, 'unknown')
        ORDER BY kind
        """
    ).fetchall()

print(
    f"updated={n} official_product={official_product}"
    f" suggested_product={suggested_product} no_product_type={no_product}"
)
for row in by_kind:
    print(f"  clover_tag_{row['kind']}={row['n']}")
