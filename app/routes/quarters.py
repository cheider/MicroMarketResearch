"""
Quarter analysis blueprint.

Routes:
  GET  /analysis/quarters              — comparison dashboard
  GET  /analysis/quarters/manage       — list + create quarters
  POST /analysis/quarters/manage       — create a quarter
  POST /analysis/quarters/<id>/delete  — delete a quarter
"""

import json

from flask import (
    Blueprint,
    flash,
    redirect,
    request,
    url_for,
)

from app.render import render_app_template

from app.analysis.quarter_analytics import (
    compare_quarters,
    create_quarter,
    delete_quarter,
    get_all_quarters,
    get_quarter_by_id,
)

quarters_bp = Blueprint("quarters", __name__)


# ---------------------------------------------------------------------------
# Comparison dashboard
# ---------------------------------------------------------------------------

@quarters_bp.route("/analysis/quarters")
def quarter_comparison():
    quarters = get_all_quarters()

    q1_id = request.args.get("q1", type=int)
    q2_id = request.args.get("q2", type=int)

    comparison = None
    chart_labels = []
    chart_q1_revenue = []
    chart_q2_revenue = []
    chart_q1_profit = []
    chart_q2_profit = []

    if q1_id and q2_id:
        comparison = compare_quarters(q1_id, q2_id)
        if comparison["weeks"]:
            chart_labels = [
                f"Week {w['week_num']}" for w in comparison["weeks"]
            ]
            chart_q1_revenue = [
                round(w["q1_revenue"] / 100, 2)
                for w in comparison["weeks"]
            ]
            chart_q2_revenue = [
                round(w["q2_revenue"] / 100, 2)
                for w in comparison["weeks"]
            ]
            chart_q1_profit = [
                round(w["q1_profit"] / 100, 2)
                for w in comparison["weeks"]
            ]
            chart_q2_profit = [
                round(w["q2_profit"] / 100, 2)
                for w in comparison["weeks"]
            ]

    return render_app_template(
        "quarters.html",
        quarters=quarters,
        q1_id=q1_id,
        q2_id=q2_id,
        comparison=comparison,
        chart_labels=json.dumps(chart_labels),
        chart_q1_revenue=json.dumps(chart_q1_revenue),
        chart_q2_revenue=json.dumps(chart_q2_revenue),
        chart_q1_profit=json.dumps(chart_q1_profit),
        chart_q2_profit=json.dumps(chart_q2_profit),
    )


# ---------------------------------------------------------------------------
# Quarter management
# ---------------------------------------------------------------------------

@quarters_bp.route("/analysis/quarters/manage", methods=["GET"])
def manage_quarters():
    quarters = get_all_quarters()
    return render_app_template("quarters_manage.html", quarters=quarters)


@quarters_bp.route("/analysis/quarters/manage", methods=["POST"])
def create_quarter_route():
    school_year = request.form.get("school_year", "").strip()
    season = request.form.get("season", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if not all([school_year, season, start_date, end_date]):
        flash("All fields are required.", "danger")
        return redirect(url_for("quarters.manage_quarters"))

    try:
        create_quarter(school_year, season, start_date, end_date)
        flash(
            f"{season} {school_year} quarter created successfully.",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("quarters.manage_quarters"))


@quarters_bp.route(
    "/analysis/quarters/<int:quarter_id>/delete", methods=["POST"]
)
def delete_quarter_route(quarter_id: int):
    q = get_quarter_by_id(quarter_id)
    if q:
        delete_quarter(quarter_id)
        flash(
            f"{q['season']} {q['school_year']} quarter deleted.",
            "success",
        )
    else:
        flash("Quarter not found.", "danger")
    return redirect(url_for("quarters.manage_quarters"))
