from flask import Blueprint, request

from app.render import render_app_template

from app.analysis.shrinkage import get_shrinkage_report

shrinkage_bp = Blueprint("shrinkage", __name__)


@shrinkage_bp.route("/analysis/shrinkage")
def shrinkage():
    days = int(request.args.get("days", 30))

    df = get_shrinkage_report(days=days)

    if df.empty:
        rows = []
        alert_rows = []
    else:
        display_cols = [
            "item_id", "name",
            "opening_stock", "closing_stock", "units_sold",
            "expected_stock", "shrinkage_units", "shrinkage_value_cents",
        ]
        existing = [c for c in display_cols if c in df.columns]
        rows = df[existing].to_dict(orient="records")
        alert_rows = [r for r in rows if r.get("shrinkage_units", 0) > 0]

    return render_app_template(
        "shrinkage.html",
        rows=rows,
        alert_rows=alert_rows,
        days=days,
    )
