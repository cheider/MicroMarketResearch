import json
from flask import Blueprint, render_template, jsonify, abort

from app.analysis.margins import get_item_margin
from app.analysis.shrinkage import get_item_shrinkage
from app.analysis.velocity import get_item_sales_series

item_bp = Blueprint("item", __name__)


@item_bp.route("/item/<item_id>")
def item_detail(item_id):
    margin = get_item_margin(item_id)
    if not margin:
        abort(404)

    shrinkage = get_item_shrinkage(item_id, days=30)
    sales_series = get_item_sales_series(item_id, days=30)

    return render_template(
        "item_detail.html",
        item=margin,
        shrinkage=shrinkage,
        sales_series_json=json.dumps(sales_series),
    )


@item_bp.route("/api/chart/<item_id>/sales")
def item_sales_chart(item_id):
    days = 30
    series = get_item_sales_series(item_id, days=days)
    return jsonify(series)
