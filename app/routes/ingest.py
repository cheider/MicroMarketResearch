from flask import Blueprint, request, jsonify, current_app

from app.etl.ingest import run_full_ingest, run_incremental_ingest
from app.database import get_connection

ingest_bp = Blueprint("ingest", __name__)


@ingest_bp.route("/ingest", methods=["POST"])
def trigger_ingest():
    client = current_app.extensions["clover_client"]
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "incremental")
    days = int(body.get("days", 30))

    try:
        if mode == "full":
            result = run_full_ingest(client, days=days)
        else:
            result = run_incremental_ingest(client, days=days)
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@ingest_bp.route("/ingest/status", methods=["GET"])
def ingest_status():
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, sync_ts, sync_type, records_fetched, status, error_detail
            FROM sync_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return jsonify({"status": "no_sync_found"}), 200

    return jsonify(dict(row)), 200
