"""Read last Clover sync from sync_log (no API calls)."""

from app.database import get_connection


def get_last_sync() -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT sync_ts, sync_type, status, records_fetched, error_detail
            FROM sync_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    return dict(row)
