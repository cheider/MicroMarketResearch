import os

from dotenv import set_key
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app,
)

from app.clover.client import CloverClient
from app.database import get_connection

settings_bp = Blueprint("settings", __name__)

_KNOWN_BASE_URLS = {
    "https://api.clover.com",
    "https://apisandbox.dev.clover.com",
}

ENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)


def _get_sync_log() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, sync_ts, sync_type, status,
                   records_fetched, error_detail
            FROM sync_log
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()
    return [dict(r) for r in rows]


@settings_bp.route("/settings", methods=["GET"])
def settings():
    cfg = current_app.extensions["app_config"]
    base_url = cfg.CLOVER_BASE_URL
    is_custom = base_url not in _KNOWN_BASE_URLS
    sync_log = _get_sync_log()

    return render_template(
        "settings.html",
        merchant_id=cfg.CLOVER_MERCHANT_ID,
        base_url=base_url,
        is_custom=is_custom,
        sync_log=sync_log,
        token_is_set=bool(cfg.CLOVER_API_TOKEN),
    )


@settings_bp.route("/settings", methods=["POST"])
def settings_save():
    cfg = current_app.extensions["app_config"]

    new_token = request.form.get("clover_api_token", "").strip()
    new_merchant_id = request.form.get("clover_merchant_id", "").strip()
    base_url_select = request.form.get("clover_base_url_select", "").strip()
    base_url_custom = request.form.get("clover_base_url_custom", "").strip()

    if base_url_select == "custom":
        new_base_url = base_url_custom
    else:
        new_base_url = base_url_select

    if not new_merchant_id:
        flash("Merchant ID cannot be blank.", "danger")
        return redirect(url_for("settings.settings"))

    if new_base_url and not new_base_url.startswith("http"):
        flash("Base URL must start with http:// or https://", "danger")
        return redirect(url_for("settings.settings"))

    changed = []

    if new_token:
        set_key(ENV_PATH, "CLOVER_API_TOKEN", new_token)
        os.environ["CLOVER_API_TOKEN"] = new_token
        object.__setattr__(cfg, "CLOVER_API_TOKEN", new_token)
        changed.append("API token")

    if new_merchant_id != cfg.CLOVER_MERCHANT_ID:
        set_key(ENV_PATH, "CLOVER_MERCHANT_ID", new_merchant_id)
        os.environ["CLOVER_MERCHANT_ID"] = new_merchant_id
        object.__setattr__(cfg, "CLOVER_MERCHANT_ID", new_merchant_id)
        changed.append("Merchant ID")

    if new_base_url and new_base_url != cfg.CLOVER_BASE_URL:
        set_key(ENV_PATH, "CLOVER_BASE_URL", new_base_url)
        os.environ["CLOVER_BASE_URL"] = new_base_url
        object.__setattr__(cfg, "CLOVER_BASE_URL", new_base_url)
        changed.append("Base URL")

    if changed:
        current_app.extensions["clover_client"] = CloverClient(cfg)

    if changed:
        flash(f"Settings saved: {', '.join(changed)}.", "success")
    else:
        flash("No changes detected.", "info")

    return redirect(url_for("settings.settings"))
