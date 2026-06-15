"""
CSV export/import for product category assignments.
"""

from __future__ import annotations

import csv
import io
from typing import BinaryIO, TextIO

import pandas as pd

from app.analysis.item_context import infer_supplier
from app.database import get_connection
from app.inventory_tools.categorization_service import apply_manual_assignments
from app.taxonomy import PRODUCT_SLUGS

CATEGORIZATION_CSV_COLUMNS = [
    "item_id",
    "item_name",
    "product_category_id",
    "product_category_name",
    "category_board_sort",
    "product_category_source",
    "clover_category",
    "supplier_inferred",
    "notes",
]


def export_categorization_csv(
    include_inactive: bool = False,
) -> str:
    clause = "" if include_inactive else "WHERE i.is_active = 1"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                i.item_id,
                i.name AS item_name,
                i.product_category_id,
                pc.name AS product_category_name,
                i.category_board_sort,
                i.product_category_source,
                c.name AS clover_category
            FROM items i
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            {clause}
            ORDER BY i.name
            """
        ).fetchall()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CATEGORIZATION_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "item_id": row["item_id"],
            "item_name": row["item_name"],
            "product_category_id": row["product_category_id"] or "",
            "product_category_name": row["product_category_name"] or "",
            "category_board_sort": row["category_board_sort"] or "",
            "product_category_source": row["product_category_source"] or "",
            "clover_category": row["clover_category"] or "",
            "supplier_inferred": infer_supplier(
                row["clover_category"], row["item_name"]
            ),
            "notes": "",
        })
    return buf.getvalue()


def import_categorization_csv(
    file_obj: TextIO | BinaryIO,
    move_missing_to_uncategorized: bool = False,
) -> dict:
    if hasattr(file_obj, "read"):
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
    else:
        content = str(file_obj)

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return {
            "updated": 0,
            "errors": [{"row": 0, "error": "empty CSV"}],
            "not_in_csv_unchanged": 0,
            "not_in_csv_item_ids": [],
        }

    field_map = {h.strip().lower(): h for h in reader.fieldnames if h}
    required = {"item_id", "product_category_id"}
    missing_cols = required - set(field_map)
    if missing_cols:
        return {
            "updated": 0,
            "errors": [{
                "row": 0,
                "error": f"missing columns: {', '.join(sorted(missing_cols))}",
            }],
            "not_in_csv_unchanged": 0,
            "not_in_csv_item_ids": [],
        }

    assignments = []
    errors = []
    imported_ids: set[str] = set()
    row_num = 1

    for row in reader:
        row_num += 1
        item_id = (row.get(field_map["item_id"]) or "").strip()
        slug = (row.get(field_map["product_category_id"]) or "").strip()
        sort_key = field_map.get("category_board_sort")
        sort_raw = row.get(sort_key, "") if sort_key else ""
        try:
            sort_val = int(sort_raw) if str(sort_raw).strip() != "" else 0
        except ValueError:
            sort_val = 0

        if not item_id:
            errors.append({"row": row_num, "error": "missing item_id"})
            continue
        if slug and slug not in PRODUCT_SLUGS:
            errors.append({
                "row": row_num,
                "item_id": item_id,
                "error": f"unknown product_category_id: {slug}",
            })
            continue

        imported_ids.add(item_id)
        assignments.append({
            "item_id": item_id,
            "product_category_id": slug or None,
            "sort": sort_val,
        })

    result = apply_manual_assignments(assignments)
    errors.extend(result.get("errors", []))

    with get_connection() as conn:
        active_rows = conn.execute(
            "SELECT item_id FROM items WHERE is_active = 1"
        ).fetchall()
        all_ids = {r["item_id"] for r in active_rows}
        not_in_csv = sorted(all_ids - imported_ids)

        if move_missing_to_uncategorized and not_in_csv:
            for idx, missing_id in enumerate(not_in_csv):
                apply_manual_assignments([{
                    "item_id": missing_id,
                    "product_category_id": "uncategorized",
                    "sort": idx,
                }])
            result["updated"] += len(not_in_csv)

    return {
        "updated": result["updated"],
        "errors": errors,
        "not_in_csv_unchanged": len(not_in_csv) if not move_missing_to_uncategorized else 0,
        "not_in_csv_item_ids": not_in_csv if not move_missing_to_uncategorized else [],
        "moved_to_uncategorized": len(not_in_csv) if move_missing_to_uncategorized else 0,
    }


def categorization_dataframe(include_inactive: bool = False) -> pd.DataFrame:
    csv_text = export_categorization_csv(include_inactive=include_inactive)
    return pd.read_csv(io.StringIO(csv_text))
