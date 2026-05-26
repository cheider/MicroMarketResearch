import threading
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app

from app.etl.ingest import run_full_ingest, run_incremental_ingest
from app.database import get_connection

ingest_bp = Blueprint("ingest", __name__)

# ---------------------------------------------------------------------------
# Progress store (in-memory, process-lifetime)
# ---------------------------------------------------------------------------

_jobs: dict = {}
_jobs_lock = threading.Lock()

STAGES = [
    "categories",
    "items",
    "orders",
    "line_items",
    "daily_sales",
    "stock",
    "log",
]


def _new_job(job_id: str, mode: str) -> dict:
    return {
        "job_id": job_id,
        "mode": mode,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "overall_status": "running",
        "error_message": None,
        "result": None,
        "stages": {
            s: {"status": "pending", "count": None, "detail": None}
            for s in STAGES
        },
    }


def _make_progress_callback(job_id: str):
    def on_progress(stage_id: str, status: str, count=None, detail=None):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["stages"][stage_id] = {
                    "status": status,
                    "count": count,
                    "detail": detail,
                }
    return on_progress


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@ingest_bp.route("/ingest", methods=["POST"])
def trigger_ingest():
    client = current_app.extensions["clover_client"]
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "incremental")
    days = int(body.get("days", current_app.config.get("INGEST_LOOKBACK_DAYS", 90)))

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = _new_job(job_id, mode)

    on_progress = _make_progress_callback(job_id)

    def run_job():
        try:
            if mode == "full":
                result = run_full_ingest(
                    client, days=days, on_progress=on_progress
                )
            else:
                result = run_incremental_ingest(
                    client, days=days, on_progress=on_progress
                )
            with _jobs_lock:
                _jobs[job_id]["overall_status"] = "done"
                _jobs[job_id]["result"] = result
        except Exception as exc:
            with _jobs_lock:
                _jobs[job_id]["overall_status"] = "error"
                _jobs[job_id]["error_message"] = str(exc)[:500]

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"status": "started", "job_id": job_id}), 202


@ingest_bp.route("/ingest/progress/<job_id>", methods=["GET"])
def ingest_progress(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job), 200


@ingest_bp.route("/ingest/status", methods=["GET"])
def ingest_status():
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, sync_ts, sync_type, records_fetched,
                   status, error_detail
            FROM sync_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return jsonify({"status": "no_sync_found"}), 200

    return jsonify(dict(row)), 200
