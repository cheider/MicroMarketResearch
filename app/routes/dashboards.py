"""
Routes for the three main dashboards: Sales, Inventory Turnover, and Profit.
"""

import io
from datetime import date

import pandas as pd
from flask import Blueprint, render_template, request, make_response

from app.analysis.dashboard_analytics import (
    get_all_categories,
    get_sales_stats,
    get_sales_by_category,
    get_top_products,
    get_inventory_stats,
    get_stock_by_category,
    get_turnover_by_category,
    get_low_stock_items,
    get_stock_chart_data,
    get_profit_stats,
    get_profit_by_category,
    get_weekly_profit,
)

dashboards_bp = Blueprint("dashboards", __name__)


def _period_param() -> str:
    period = request.args.get("period", "week")
    return period if period in ("week", "lastweek") else "week"


def _category_param() -> str | None:
    val = request.args.get("category_id", "").strip()
    return val if val else None


# ---------------------------------------------------------------------------
# Sales dashboard
# ---------------------------------------------------------------------------

@dashboards_bp.route("/dashboards/sales")
def sales_dashboard():
    period = _period_param()
    category_id = _category_param()

    stats = get_sales_stats(period=period, category_id=category_id)
    by_category = get_sales_by_category(period=period, category_id=category_id)
    top_products = get_top_products(period=period, category_id=category_id)
    categories = get_all_categories()

    return render_template(
        "sales_dashboard.html",
        period=period,
        category_id=category_id,
        stats=stats,
        by_category=by_category,
        top_products=top_products,
        categories=categories,
    )


@dashboards_bp.route("/dashboards/sales/download")
def sales_download():
    period = _period_param()
    category_id = _category_param()

    top_products = get_top_products(period=period, category_id=category_id, top_n=1000)
    df = pd.DataFrame(top_products) if top_products else pd.DataFrame(
        columns=["item_id", "name", "units_sold", "revenue_cents"]
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False)

    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=sales_{date.today().isoformat()}.csv"
    )
    return response


# ---------------------------------------------------------------------------
# Inventory Turnover dashboard
# ---------------------------------------------------------------------------

@dashboards_bp.route("/dashboards/inventory")
def inventory_dashboard():
    period = _period_param()

    stats = get_inventory_stats(period=period)
    by_category = get_stock_by_category()
    turnover_by_cat = get_turnover_by_category(period=period)
    low_stock = get_low_stock_items(threshold=10)
    chart = get_stock_chart_data(top_n=20)
    categories = get_all_categories()

    return render_template(
        "inventory_dashboard.html",
        period=period,
        stats=stats,
        by_category=by_category,
        turnover_by_cat=turnover_by_cat,
        low_stock=low_stock,
        chart=chart,
        categories=categories,
    )


@dashboards_bp.route("/dashboards/inventory/download")
def inventory_download():
    low_stock = get_low_stock_items(threshold=10)
    by_category = get_stock_by_category()

    rows = by_category if by_category else []
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["category_id", "name", "total_stock"]
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False)

    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=inventory_{date.today().isoformat()}.csv"
    )
    return response


# ---------------------------------------------------------------------------
# Profit dashboard
# ---------------------------------------------------------------------------

@dashboards_bp.route("/dashboards/profit")
def profit_dashboard():
    period = _period_param()
    category_id = _category_param()

    stats = get_profit_stats(period=period, category_id=category_id)
    by_category = get_profit_by_category(period=period)
    weekly = get_weekly_profit(weeks=8)
    categories = get_all_categories()

    return render_template(
        "profit_dashboard.html",
        period=period,
        category_id=category_id,
        stats=stats,
        by_category=by_category,
        weekly=weekly,
        categories=categories,
    )


@dashboards_bp.route("/dashboards/profit/download")
def profit_download():
    period = _period_param()
    category_id = _category_param()

    by_category = get_profit_by_category(period=period)
    df = pd.DataFrame(by_category) if by_category else pd.DataFrame(
        columns=["category_id", "name", "revenue_cents", "cost_cents", "margin_pct"]
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False)

    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=profit_{date.today().isoformat()}.csv"
    )
    return response
