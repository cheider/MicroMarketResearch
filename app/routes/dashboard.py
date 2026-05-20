from flask import Blueprint, redirect, url_for

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboards.sales_dashboard"))
