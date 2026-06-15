"""
Optional periodic incremental sync while Flask is running.

Only runs when AUTO_SYNC_INTERVAL_MINUTES > 0 in config.
"""

import logging
import threading

logger = logging.getLogger(__name__)

_timer: threading.Timer | None = None
_lock = threading.Lock()


def _run_incremental(app):
    with app.app_context():
        from app.etl.ingest import run_incremental_ingest

        cfg = app.extensions["app_config"]
        days = app.config.get("INGEST_LOOKBACK_DAYS", 90)
        try:
            run_incremental_ingest(
                app.extensions["clover_client"],
                days=days,
            )
            logger.info("Auto-sync completed (%s days lookback)", days)
        except Exception as exc:
            logger.warning("Auto-sync failed: %s", exc)


def _schedule_next(app, interval_seconds: float):
    global _timer

    def _tick():
        _run_incremental(app)
        _schedule_next(app, interval_seconds)

    with _lock:
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(interval_seconds, _tick)
        _timer.daemon = True
        _timer.start()


def start_auto_sync(app) -> None:
    minutes = app.config.get("AUTO_SYNC_INTERVAL_MINUTES", 0)
    if not minutes or minutes <= 0:
        return
    interval_seconds = float(minutes) * 60.0
    logger.info("Auto-sync enabled: every %s minutes", minutes)
    _schedule_next(app, interval_seconds)


def stop_auto_sync() -> None:
    global _timer
    with _lock:
        if _timer:
            _timer.cancel()
            _timer = None
