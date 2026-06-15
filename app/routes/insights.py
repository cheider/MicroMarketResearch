import io
from datetime import date

import pandas as pd
from flask import Blueprint, request, make_response, redirect, url_for, flash, g

from app.render import render_app_template, scrub_if_demo

from app.analysis.periods import normalize_period, resolve_period
from app.analysis.seasonal import (
    get_day_of_week_profile,
    get_week_over_week,
    get_calendar_window_comparison,
    get_category_mix_shift,
    get_insights_summary,
)
from app.analysis.projections import (
    reorder_suggestions,
    stockout_risk_items,
    get_forecast_summary,
)
from app.analysis.calendar import get_all_events

insights_bp = Blueprint("insights", __name__)


def _period_param() -> str:
    return normalize_period(request.args.get("period", "30d"))


@insights_bp.route("/analysis/insights")
def insights_dashboard():
    ux = g.get("ux")
    if ux and not ux.show_insights_nav:
        flash("Insights is hidden in the current UI preset. Switch preset in the sidebar.", "info")
        return redirect(url_for("dashboards.sales_dashboard"))

    period = _period_param()
    period_info = resolve_period(period)
    event_id = request.args.get("event_id", "").strip()

    summary = get_insights_summary(period)
    dow = get_day_of_week_profile(period)
    wow = get_week_over_week("7d")
    mix = get_category_mix_shift(period)
    events = get_all_events()

    calendar_cmp = None
    if event_id:
        calendar_cmp = get_calendar_window_comparison(event_id)
    elif events:
        calendar_cmp = get_calendar_window_comparison(events[0]["id"])

    reorder = reorder_suggestions()
    stockout = stockout_risk_items()
    forecast = get_forecast_summary(horizon_days=14)

    return render_app_template(
        "insights.html",
        period=period,
        period_info=period_info,
        summary=summary,
        dow=dow,
        wow=wow,
        mix=mix,
        events=events,
        selected_event_id=event_id or (events[0]["id"] if events else ""),
        calendar_cmp=calendar_cmp,
        reorder=reorder,
        stockout=stockout,
        forecast=forecast,
    )


@insights_bp.route("/analysis/insights/reorder/download")
def reorder_download():
    rows = scrub_if_demo(reorder_suggestions())
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=[
            "item_id", "name", "avg_daily_units", "on_hand",
            "days_until_stockout", "suggested_reorder_qty",
        ]
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=reorder_{date.today().isoformat()}.csv"
    )
    return response
