"""Category analysis routes."""

from __future__ import annotations

from flask import Blueprint, request

from app.analysis.category_analysis import get_category_analysis_report
from app.analysis.periods import normalize_period
from app.render import render_app_template

category_analysis_bp = Blueprint("category_analysis", __name__)


@category_analysis_bp.route("/analysis/categories")
def category_analysis_overview():
    period = normalize_period(request.args.get("period", "90d"))
    report = get_category_analysis_report(period=period)
    return render_app_template(
        "category_analysis/overview.html",
        **report,
    )
