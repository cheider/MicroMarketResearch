import os

from dotenv import set_key
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app, make_response,
)

from app.clover.client import CloverClient
from app.database import get_connection
from datetime import date

from app.analysis.calendar import (
    get_all_events,
    get_calendar_meta,
    upsert_academic_event,
    delete_academic_event,
    save_calendar_json,
    sync_estimated_events_to_db,
)
from app.ux.variants import COOKIE_NAME, get_variant

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

    cal = get_calendar_meta()
    return render_template(
        "settings.html",
        merchant_id=cfg.CLOVER_MERCHANT_ID,
        base_url=base_url,
        is_custom=is_custom,
        sync_log=sync_log,
        token_is_set=bool(cfg.CLOVER_API_TOKEN),
        calendar_events=get_all_events(),
        calendar_meta=cal,
        ingest_lookback_days=cfg.INGEST_LOOKBACK_DAYS,
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


@settings_bp.route("/settings/calendar/term", methods=["POST"])
def settings_calendar_term():
    term = request.form.get("term_label", "").strip()
    quarter_start = request.form.get("quarter_start", "").strip()
    quarter_end = request.form.get("quarter_end", "").strip()
    auto_estimate = request.form.get("auto_estimate_events") == "on"
    sync_now = request.form.get("sync_estimates") == "on"

    if not quarter_start or not quarter_end:
        flash("Quarter start and end dates are required.", "danger")
        return redirect(url_for("settings.settings"))

    try:
        date.fromisoformat(quarter_start)
        date.fromisoformat(quarter_end)
    except ValueError:
        flash("Dates must be YYYY-MM-DD.", "danger")
        return redirect(url_for("settings.settings"))

    save_calendar_json(term, quarter_start, quarter_end, auto_estimate)

    set_key(ENV_PATH, "SEMESTER_START_DATE", quarter_start)
    os.environ["SEMESTER_START_DATE"] = quarter_start
    set_key(ENV_PATH, "TERM_END_DATE", quarter_end)
    os.environ["TERM_END_DATE"] = quarter_end

    if sync_now and auto_estimate:
        try:
            sync_estimated_events_to_db()
            flash(
                f"Term saved ({quarter_start} to {quarter_end}). "
                "Estimated midterms, break, and finals written to the calendar.",
                "success",
            )
        except ValueError as exc:
            flash(f"Term dates saved but estimates failed: {exc}", "warning")
    else:
        flash(
            f"Term saved ({quarter_start} to {quarter_end}). "
            "Check preview below; use Save & sync estimates to load Insights.",
            "success",
        )

    return redirect(url_for("settings.settings"))


@settings_bp.route("/settings/calendar", methods=["POST"])
def settings_calendar_save():
    event_id = request.form.get("event_id", "").strip()
    label = request.form.get("label", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    event_type = request.form.get("event_type", "other").strip()

    if not all([event_id, label, start_date, end_date]):
        flash("Calendar event requires ID, label, start, and end dates.", "danger")
        return redirect(url_for("settings.settings"))

    upsert_academic_event(event_id, label, start_date, end_date, event_type)
    flash(f"Calendar event '{label}' saved.", "success")
    return redirect(url_for("settings.settings"))


@settings_bp.route("/settings/ux", methods=["POST"])
def settings_ux_variant():
    variant_id = request.form.get("ux_variant", "").strip()
    v = get_variant(variant_id)
    flash(f"UI preset: {v.label}", "info")
    next_url = request.form.get("next") or url_for("dashboards.sales_dashboard")
    resp = make_response(redirect(next_url))
    resp.set_cookie(COOKIE_NAME, v.id, max_age=60 * 60 * 24 * 30, samesite="Lax")
    return resp


@settings_bp.route("/settings/calendar/delete", methods=["POST"])
def settings_calendar_delete():
    event_id = request.form.get("event_id", "").strip()
    if event_id:
        delete_academic_event(event_id)
        flash("Calendar event removed.", "success")
    return redirect(url_for("settings.settings"))
