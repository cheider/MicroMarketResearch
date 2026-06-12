"""
Quarter analytics functions.

Quarters are school-year based (Spring/Summer/Fall/Winter) with manually
set start/end dates. Week-of-quarter numbering starts at 1 from the
quarter's start_date, allowing cross-quarter comparison by aligned week.
"""

import math
import sqlite3
from datetime import date

import pandas as pd

from app.database import get_connection

VALID_SEASONS = ("Spring", "Summer", "Fall", "Winter")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _total_weeks(start_date_str: str, end_date_str: str) -> int:
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return max(1, math.ceil((end - start).days / 7))


def _week_bounds(
    week_num: int, start_date_str: str
) -> tuple[str, str]:
    """Return (week_start_iso, week_end_iso) for a given week number."""
    start = date.fromisoformat(start_date_str)
    week_start = start + __import__("datetime").timedelta(
        days=(week_num - 1) * 7
    )
    week_end = week_start + __import__("datetime").timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_all_quarters() -> list[dict]:
    """Returns all quarters ordered by school_year desc, then season."""
    season_order = "CASE season " + " ".join(
        f"WHEN '{s}' THEN {i}"
        for i, s in enumerate(("Fall", "Winter", "Spring", "Summer"))
    ) + " END"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, school_year, season, start_date, end_date
            FROM quarters
            ORDER BY school_year DESC, {season_order}
            """
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["total_weeks"] = _total_weeks(d["start_date"], d["end_date"])
        d["label"] = f"{d['season']} {d['school_year']}"
        result.append(d)
    return result


def get_quarter_by_id(quarter_id: int) -> dict | None:
    """Returns a single quarter dict or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, school_year, season, start_date, end_date "
            "FROM quarters WHERE id = ?",
            (quarter_id,),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["total_weeks"] = _total_weeks(d["start_date"], d["end_date"])
    d["label"] = f"{d['season']} {d['school_year']}"
    return d


def create_quarter(
    school_year: str,
    season: str,
    start_date: str,
    end_date: str,
) -> int:
    """
    Insert a new quarter. Returns the new row id.

    Raises ValueError for invalid season, bad date order, or duplicate.
    """
    if season not in VALID_SEASONS:
        raise ValueError(
            f"season must be one of {VALID_SEASONS}, got {season!r}"
        )
    try:
        s = date.fromisoformat(start_date)
        e = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {exc}") from exc
    if e <= s:
        raise ValueError("end_date must be after start_date")

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO quarters
                    (school_year, season, start_date, end_date)
                VALUES (?, ?, ?, ?)
                """,
                (school_year, season, start_date, end_date),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"Quarter {season} {school_year} already exists."
        ) from exc


def delete_quarter(quarter_id: int) -> None:
    """Delete a quarter by id."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM quarters WHERE id = ?", (quarter_id,)
        )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_quarter_weekly_revenue(quarter_id: int) -> list[dict]:
    """
    Returns week-by-week sales data for a quarter.

    Each row: {week_num, week_start, week_end,
               revenue_cents, units_sold, profit_cents}
    Weeks with no sales are included with zeros.
    """
    quarter = get_quarter_by_id(quarter_id)
    if quarter is None:
        return []

    start = quarter["start_date"]
    end = quarter["end_date"]
    total_weeks = quarter["total_weeks"]

    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT
                ds.sale_date,
                SUM(ds.units_sold)                           AS units_sold,
                SUM(ds.gross_revenue_cents)                  AS revenue_cents,
                SUM(
                    CASE WHEN i.cost_cents IS NOT NULL
                    THEN ds.units_sold * (i.price_cents - i.cost_cents)
                    ELSE 0 END
                )                                            AS profit_cents
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            WHERE ds.sale_date BETWEEN :start AND :end
            GROUP BY ds.sale_date
            ORDER BY ds.sale_date
            """,
            conn,
            params={"start": start, "end": end},
        )

    # Assign week numbers
    start_d = date.fromisoformat(start)
    if not df.empty:
        df["week_num"] = df["sale_date"].apply(
            lambda d: (date.fromisoformat(d) - start_d).days // 7 + 1
        )
        weekly = (
            df.groupby("week_num")
            .agg(
                revenue_cents=("revenue_cents", "sum"),
                units_sold=("units_sold", "sum"),
                profit_cents=("profit_cents", "sum"),
            )
            .reset_index()
        )
        week_map = {
            int(row["week_num"]): {
                "revenue_cents": int(row["revenue_cents"]),
                "units_sold": int(row["units_sold"]),
                "profit_cents": int(row["profit_cents"]),
            }
            for _, row in weekly.iterrows()
        }
    else:
        week_map = {}

    result = []
    for wk in range(1, total_weeks + 1):
        ws, we = _week_bounds(wk, start)
        data = week_map.get(wk, {
            "revenue_cents": 0,
            "units_sold": 0,
            "profit_cents": 0,
        })
        result.append({
            "week_num": wk,
            "week_start": ws,
            "week_end": we,
            **data,
        })
    return result


def compare_quarters(q1_id: int, q2_id: int) -> dict:
    """
    Returns a side-by-side week-aligned comparison of two quarters.

    Return structure:
    {
        "q1": quarter dict,
        "q2": quarter dict,
        "weeks": [
            {
                week_num, q1_revenue, q2_revenue, revenue_delta,
                q1_profit, q2_profit, profit_delta,
                q1_units, q2_units
            },
            ...
        ]
    }
    Weeks missing in the shorter quarter default to 0.
    """
    q1 = get_quarter_by_id(q1_id)
    q2 = get_quarter_by_id(q2_id)
    if q1 is None or q2 is None:
        return {"q1": q1, "q2": q2, "weeks": []}

    q1_weeks = {
        w["week_num"]: w
        for w in get_quarter_weekly_revenue(q1_id)
    }
    q2_weeks = {
        w["week_num"]: w
        for w in get_quarter_weekly_revenue(q2_id)
    }

    total = max(
        (max(q1_weeks) if q1_weeks else 0),
        (max(q2_weeks) if q2_weeks else 0),
    )

    rows = []
    for wk in range(1, total + 1):
        w1 = q1_weeks.get(wk, {
            "revenue_cents": 0, "profit_cents": 0, "units_sold": 0
        })
        w2 = q2_weeks.get(wk, {
            "revenue_cents": 0, "profit_cents": 0, "units_sold": 0
        })
        rows.append({
            "week_num": wk,
            "q1_revenue": w1["revenue_cents"],
            "q2_revenue": w2["revenue_cents"],
            "revenue_delta": w2["revenue_cents"] - w1["revenue_cents"],
            "q1_profit": w1["profit_cents"],
            "q2_profit": w2["profit_cents"],
            "profit_delta": w2["profit_cents"] - w1["profit_cents"],
            "q1_units": w1["units_sold"],
            "q2_units": w2["units_sold"],
        })

    return {"q1": q1, "q2": q2, "weeks": rows}
