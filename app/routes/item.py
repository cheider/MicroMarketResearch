import json
from flask import Blueprint, render_template, jsonify, abort, request, redirect, url_for, flash

from app.analysis.item_context import get_item_profile
from app.analysis.shrinkage import get_item_shrinkage
from app.analysis.velocity import get_item_sales_series
from app.item_settings import set_item_track_inventory

item_bp = Blueprint("item", __name__)


@item_bp.route("/item/<item_id>")
def item_detail(item_id):
    profile = get_item_profile(item_id)
    if not profile:
        abort(404)

    shrinkage = None
    if profile.get("track_inventory", True):
        shrinkage = get_item_shrinkage(item_id, days=30)
    sales_series = get_item_sales_series(item_id, days=30)

    return render_template(
        "item_detail.html",
        item=profile,
        shrinkage=shrinkage,
        sales_series_json=json.dumps(sales_series),
    )


@item_bp.route("/item/<item_id>/track-inventory", methods=["POST"])
def item_track_inventory(item_id):
    track = request.form.get("track_inventory") == "1"
    if not set_item_track_inventory(item_id, track):
        abort(404)
    if track:
        flash("Item included in inventory alerts and reorder planning.", "success")
    else:
        flash(
            "Item excluded from low-stock alerts, turnover, reorder, and shrinkage.",
            "info",
        )
    next_url = request.form.get("next") or url_for("item.item_detail", item_id=item_id)
    return redirect(next_url)


@item_bp.route("/api/chart/<item_id>/sales")
def item_sales_chart(item_id):
    days = 30
    series = get_item_sales_series(item_id, days=days)
    return jsonify(series)
