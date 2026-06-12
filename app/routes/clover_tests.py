"""
Clover API stress-test routes (read-only GETs, background jobs).
"""

import threading
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.clover.client import CloverClient
from app.clover.stress_tests import PROFILES, list_profiles, run_stress_suite

clover_tests_bp = Blueprint("clover_tests", __name__)

_jobs: dict = {}
_jobs_lock = threading.Lock()


def _new_job(job_id: str, profile: str) -> dict:
    return {
        "job_id": job_id,
        "profile": profile,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "overall_status": "running",
        "error_message": None,
        "result": None,
        "checks": {},
    }


def _progress_callback(job_id: str):
    def on_progress(name: str, status: str, detail: dict | None = None):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["checks"][name] = {"status": status, "detail": detail}

    return on_progress


@clover_tests_bp.route("/api/clover-tests/profiles", methods=["GET"])
def clover_test_profiles():
    return jsonify({"profiles": list_profiles()}), 200


@clover_tests_bp.route("/api/clover-tests/start", methods=["POST"])
def clover_test_start():
    cfg = current_app.extensions["app_config"]
    if not cfg.CLOVER_API_TOKEN or not cfg.CLOVER_MERCHANT_ID:
        return jsonify({"error": "CLOVER_API_TOKEN and CLOVER_MERCHANT_ID required"}), 400

    body = request.get_json(silent=True) or {}
    profile = (body.get("profile") or "light").strip()
    if profile not in PROFILES:
        return jsonify({"error": f"Unknown profile {profile!r}"}), 400

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = _new_job(job_id, profile)

    client = current_app.extensions["clover_client"]
    on_progress = _progress_callback(job_id)

    def run_job():
        try:
            result = run_stress_suite(
                client,
                profile,
                on_progress=on_progress,
                client_factory=lambda: CloverClient(cfg),
            )
            with _jobs_lock:
                _jobs[job_id]["overall_status"] = "done"
                _jobs[job_id]["result"] = result
        except Exception as exc:
            with _jobs_lock:
                _jobs[job_id]["overall_status"] = "error"
                _jobs[job_id]["error_message"] = str(exc)[:500]

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"status": "started", "job_id": job_id, "profile": profile}), 202


@clover_tests_bp.route("/api/clover-tests/progress/<job_id>", methods=["GET"])
def clover_test_progress(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job), 200
