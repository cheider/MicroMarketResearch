"""Inventory Tools routes: overview, category board, missing costs."""

from __future__ import annotations

import csv
import io
from datetime import date

import pandas as pd
from flask import (
    Blueprint,
    flash,
    jsonify,
    make_response,
    redirect,
    request,
    url_for,
)

from app.render import render_app_template, scrub_if_demo, demo_mode_active

from app.analysis.cost_collection import (
    get_missing_cost_items,
    missing_cost_dataframe,
)
from app.etl.auto_categorize import apply_auto_categorize, preview_auto_categorize
from app.inventory_tools.categorization_io import (
    CATEGORIZATION_CSV_COLUMNS,
    export_categorization_csv,
    import_categorization_csv,
)
from app.inventory_tools.categorization_service import (
    apply_manual_assignments,
    apply_stored_suggestions,
    get_category_board_state,
    get_inventory_tools_stats,
)

inventory_tools_bp = Blueprint("inventory_tools", __name__)


@inventory_tools_bp.route("/tools/inventory")
def inventory_overview():
    stats = get_inventory_tools_stats()
    return render_app_template("inventory_tools/overview.html", stats=stats)


@inventory_tools_bp.route("/tools/inventory/missing-costs")
def missing_costs_page():
    missing_costs = get_missing_cost_items(limit=50)
    stats = get_inventory_tools_stats()
    return render_app_template(
        "inventory_tools/missing_costs.html",
        missing_costs=missing_costs,
        stats=stats,
    )


@inventory_tools_bp.route("/tools/inventory/missing-costs/download")
def missing_costs_download():
    include_zero = request.args.get("include_zero_price", "1").strip() != "0"
    df = missing_cost_dataframe(include_zero_price=include_zero)
    if demo_mode_active():
        df = pd.DataFrame(scrub_if_demo(df.to_dict(orient="records")))

    buf = io.StringIO()
    df.to_csv(buf, index=False)

    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=missing_costs_{date.today().isoformat()}.csv"
    )
    return response


@inventory_tools_bp.route("/tools/inventory/categories")
def categories_page():
    include_inactive = request.args.get("include_inactive") == "1"
    hide_modifiers = request.args.get("hide_modifiers") == "1"
    search = request.args.get("q", "")
    board = get_category_board_state(
        include_inactive=include_inactive,
        hide_modifiers=hide_modifiers,
        search=search,
    )
    return render_app_template(
        "inventory_tools/categories.html",
        board=board,
        include_inactive=include_inactive,
        hide_modifiers=hide_modifiers,
        search=search,
    )


@inventory_tools_bp.route("/tools/inventory/categories/export")
def categories_export():
    include_inactive = request.args.get("include_inactive") == "1"
    csv_text = export_categorization_csv(include_inactive=include_inactive)
    if demo_mode_active():
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = scrub_if_demo(list(reader))
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CATEGORIZATION_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        csv_text = buf.getvalue()
    response = make_response(csv_text)
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=product_categories_{date.today().isoformat()}.csv"
    )
    return response


@inventory_tools_bp.route("/tools/inventory/categories/import", methods=["POST"])
def categories_import():
    move_missing = request.form.get("move_missing_to_uncategorized") == "1"
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to import.", "warning")
        return redirect(url_for("inventory_tools.categories_page"))

    summary = import_categorization_csv(
        upload.stream,
        move_missing_to_uncategorized=move_missing,
    )
    if summary["errors"]:
        flash(
            f"Import finished with {len(summary['errors'])} row error(s). "
            f"Updated {summary['updated']} item(s).",
            "warning",
        )
    else:
        flash(
            f"Updated {summary['updated']} item(s). "
            f"{summary['not_in_csv_unchanged']} active item(s) not in CSV left unchanged.",
            "success",
        )
    return redirect(url_for("inventory_tools.categories_page"))


@inventory_tools_bp.route("/api/inventory-tools/board")
def api_board():
    include_inactive = request.args.get("include_inactive") == "1"
    hide_modifiers = request.args.get("hide_modifiers") == "1"
    search = request.args.get("q", "")
    return jsonify(
        get_category_board_state(
            include_inactive=include_inactive,
            hide_modifiers=hide_modifiers,
            search=search,
        )
    )


@inventory_tools_bp.route("/api/inventory-tools/categorization", methods=["POST"])
def api_categorization():
    payload = request.get_json(silent=True) or {}
    assignments = payload.get("assignments") or []
    if not isinstance(assignments, list):
        return jsonify({"error": "assignments must be a list"}), 400
    result = apply_manual_assignments(assignments)
    status = 200 if not result["errors"] else 207
    return jsonify(result), status


@inventory_tools_bp.route("/api/inventory-tools/apply-suggestions", methods=["POST"])
def api_apply_suggestions():
    result = apply_stored_suggestions()
    return jsonify(result)


@inventory_tools_bp.route("/api/inventory-tools/auto-categorize/preview", methods=["POST"])
def api_auto_categorize_preview():
    only_unassigned = request.get_json(silent=True) or {}
    flag = only_unassigned.get("only_unassigned", True)
    rows = preview_auto_categorize(only_unassigned=bool(flag))
    return jsonify({"preview": rows, "count": len(rows)})


@inventory_tools_bp.route("/api/inventory-tools/auto-categorize/apply", methods=["POST"])
def api_auto_categorize_apply():
    body = request.get_json(silent=True) or {}
    only_unassigned = bool(body.get("only_unassigned", True))
    write_as_suggested = bool(body.get("write_as_suggested", False))
    updated = apply_auto_categorize(
        only_unassigned=only_unassigned,
        write_as_suggested=write_as_suggested,
    )
    return jsonify({"updated": updated})
