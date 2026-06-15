"""Local per-item settings not synced from Clover."""

from app.database import get_connection


def set_item_track_inventory(item_id: str, track: bool) -> bool:
    """Returns False if the item does not exist."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE items SET track_inventory = ? WHERE item_id = ?",
            (1 if track else 0, item_id),
        )
    return True
