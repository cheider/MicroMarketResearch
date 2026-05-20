from flask import Blueprint, render_template, request, current_app

from app.analysis.margins import get_margin_report

margins_bp = Blueprint("margins", __name__)


@margins_bp.route("/analysis/margins")
def margins():
    threshold = float(
        request.args.get("threshold", current_app.config.get("MARGIN_ALERT_THRESHOLD", 0.10))
    )
    sort = request.args.get("sort", "margin_asc")

    report = get_margin_report(threshold=threshold)

    def to_rows(df):
        if df.empty:
            return []
        cols = [c for c in ["item_id", "name", "price_dollars", "cost_dollars", "margin_pct"] if c in df.columns]
        return df[cols].to_dict(orient="records")

    return render_template(
        "margins.html",
        negative=to_rows(report["negative"]),
        low=to_rows(report["low"]),
        acceptable=to_rows(report["acceptable"]),
        no_cost_count=len(report["no_cost"]),
        threshold_pct=int(threshold * 100),
        total_items=report.get("total_items", 0),
        items_with_cost=report.get("items_with_cost", 0),
    )
