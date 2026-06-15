from flask import Blueprint, request

from app.render import render_app_template

from app.analysis.velocity import get_velocity_report

velocity_bp = Blueprint("velocity", __name__)


@velocity_bp.route("/analysis/velocity")
def velocity():
    days = int(request.args.get("days", 30))
    top_n = int(request.args.get("top", 20))

    report = get_velocity_report(days=days, top_n=top_n)

    def to_rows(df):
        if df.empty:
            return []
        cols = [c for c in ["rank", "name", "units_sold", "gross_revenue_cents", "revenue_share_pct", "price_dollars", "item_id"] if c in df.columns]
        return df[cols].to_dict(orient="records")

    return render_app_template(
        "velocity.html",
        top_sellers=to_rows(report["top_sellers"]),
        bottom_sellers=to_rows(report["bottom_sellers"]),
        total_revenue_cents=report["total_revenue_cents"],
        period_days=days,
        top_n=top_n,
    )
