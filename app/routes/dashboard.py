from flask import Blueprint, render_template, current_app

from app.analysis.margins import get_margin_report
from app.analysis.shrinkage import get_shrinkage_report
from app.analysis.velocity import get_velocity_report
from app.database import get_connection

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    threshold = current_app.config.get("MARGIN_ALERT_THRESHOLD", 0.10)

    margin_report = get_margin_report(threshold=threshold)
    shrinkage_report = get_shrinkage_report(days=30)
    velocity_report = get_velocity_report(days=30, top_n=5)

    with get_connection() as conn:
        last_sync = conn.execute(
            "SELECT sync_ts, sync_type, status, records_fetched FROM sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

    shrinkage_items = shrinkage_report[shrinkage_report["shrinkage_units"] > 0] if not shrinkage_report.empty else shrinkage_report

    return render_template(
        "dashboard.html",
        negative_count=len(margin_report["negative"]),
        low_margin_count=len(margin_report["low"]),
        total_items=margin_report.get("total_items", 0),
        shrinkage_item_count=len(shrinkage_items),
        top_sellers=velocity_report["top_sellers"].to_dict(orient="records"),
        total_revenue_cents=velocity_report["total_revenue_cents"],
        last_sync=dict(last_sync) if last_sync else None,
        threshold_pct=int(threshold * 100),
    )
