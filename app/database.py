import sqlite3
from contextlib import contextmanager

_db_path = None


def init_db(db_path: str):
    global _db_path
    _db_path = db_path
    if db_path == ":memory:":
        conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _create_schema(conn)
        _migrate(conn)
        conn.commit()
        conn.close()
    else:
        with get_connection() as conn:
            _create_schema(conn)
            _migrate(conn)


@contextmanager
def get_connection():
    if _db_path == ":memory:":
        conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    else:
        conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            last_synced   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS items (
            item_id       TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            price_cents   INTEGER NOT NULL,
            cost_cents    INTEGER,
            is_active     INTEGER DEFAULT 1,
            last_synced   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_sales (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id               TEXT NOT NULL REFERENCES items(item_id),
            sale_date             TEXT NOT NULL,
            units_sold            INTEGER NOT NULL DEFAULT 0,
            gross_revenue_cents   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(item_id, sale_date)
        );

        CREATE TABLE IF NOT EXISTS stock_snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      TEXT NOT NULL REFERENCES items(item_id),
            snapshot_ts  TEXT NOT NULL,
            quantity     INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_ts         TEXT NOT NULL,
            sync_type       TEXT NOT NULL,
            records_fetched INTEGER,
            status          TEXT NOT NULL,
            error_detail    TEXT
        );
    """)


def _migrate(conn: sqlite3.Connection):
    """Applies additive migrations safe to run on existing databases."""
    try:
        conn.execute("ALTER TABLE items ADD COLUMN category_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists


def column_audit(table: str) -> list:
    with get_connection() as conn:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return [row["name"] for row in cursor.fetchall()]
