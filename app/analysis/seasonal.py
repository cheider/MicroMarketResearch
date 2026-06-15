"""
Seasonal and academic-calendar analytics for college micro-market patterns.
"""

import pandas as pd

from app.database import get_connection
from app.analysis.periods import resolve_period, today
from app.analysis.calendar import get_event_by_id, get_all_events, events_on_date


def get_day_of_week_profile(period: str = "30d") -> dict:
    bounds = resolve_period(period)
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT sale_date,
                   SUM(gross_revenue_cents) AS revenue_cents,
                   SUM(units_sold) AS units_sold
            FROM daily_sales
            WHERE sale_date BETWEEN :start AND :end
            GROUP BY sale_date
            """,
            conn,
            params={"start": bounds["start"], "end": bounds["end"]},
        )

    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if df.empty:
        return {"labels": labels, "avg_revenue": [0] * 7, "avg_units": [0] * 7}

    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["dow"] = df["sale_date"].dt.dayofweek
    grouped = df.groupby("dow").agg(
        revenue_cents=("revenue_cents", "mean"),
        units_sold=("units_sold", "mean"),
    )
    avg_rev = []
    avg_units = []
    for i in range(7):
        if i in grouped.index:
            avg_rev.append(round(grouped.loc[i, "revenue_cents"] / 100, 2))
            avg_units.append(round(grouped.loc[i, "units_sold"], 1))
        else:
            avg_rev.append(0.0)
            avg_units.append(0.0)
    return {"labels": labels, "avg_revenue": avg_rev, "avg_units": avg_units}


def get_week_over_week(period: str = "7d") -> dict:
    bounds = resolve_period(period)
    end = pd.Timestamp(bounds["end"])
    start = pd.Timestamp(bounds["start"])
    prior_end = start - pd.Timedelta(days=1)
    prior_start = prior_end - (end - start)

    def _totals(s, e):
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(gross_revenue_cents), 0) AS rev,
                       COALESCE(SUM(units_sold), 0) AS units
                FROM daily_sales
                WHERE sale_date BETWEEN ? AND ?
                """,
                (s.date().isoformat(), e.date().isoformat()),
            ).fetchone()
        return int(row["rev"]), int(row["units"])

    cur_rev, cur_units = _totals(start, end)
    prev_rev, prev_units = _totals(prior_start, prior_end)

    def pct(cur, prev):
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round((cur - prev) / prev * 100, 1)

    with get_connection() as conn:
        cat_df = pd.read_sql(
            """
            SELECT COALESCE(pc.name, 'Uncategorized') AS name,
                   SUM(CASE WHEN ds.sale_date BETWEEN :cs AND :ce THEN ds.gross_revenue_cents ELSE 0 END) AS cur_rev,
                   SUM(CASE WHEN ds.sale_date BETWEEN :ps AND :pe THEN ds.gross_revenue_cents ELSE 0 END) AS prev_rev
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            WHERE ds.sale_date BETWEEN :ps AND :ce
            GROUP BY COALESCE(pc.name, 'Uncategorized')
            """,
            conn,
            params={
                "cs": start.date().isoformat(),
                "ce": end.date().isoformat(),
                "ps": prior_start.date().isoformat(),
                "pe": prior_end.date().isoformat(),
            },
        )

    by_category = []
    if not cat_df.empty:
        for _, row in cat_df.iterrows():
            by_category.append({
                "name": row["name"],
                "revenue_change_pct": pct(int(row["cur_rev"]), int(row["prev_rev"])),
                "current_revenue_cents": int(row["cur_rev"]),
            })
        by_category.sort(key=lambda x: x["revenue_change_pct"], reverse=True)

    return {
        "current_revenue_cents": cur_rev,
        "prior_revenue_cents": prev_rev,
        "revenue_change_pct": pct(cur_rev, prev_rev),
        "units_change_pct": pct(cur_units, prev_units),
        "by_category": by_category,
    }


def get_calendar_window_comparison(event_id: str, baseline_days: int = 14) -> dict | None:
    event = get_event_by_id(event_id)
    if not event:
        return None

    ev_start, ev_end = event["start"], event["end"]
    ev_start_ts = pd.Timestamp(ev_start)
    baseline_end = ev_start_ts - pd.Timedelta(days=1)
    baseline_start = baseline_end - pd.Timedelta(days=baseline_days - 1)

    def _avg_daily(s, e):
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(gross_revenue_cents), 0) AS rev,
                       COUNT(DISTINCT sale_date) AS days
                FROM daily_sales
                WHERE sale_date BETWEEN ? AND ?
                """,
                (s, e),
            ).fetchone()
        days = max(int(row["days"]), 1)
        return int(row["rev"]) / days

    event_avg = _avg_daily(ev_start, ev_end)
    base_avg = _avg_daily(
        baseline_start.date().isoformat(),
        baseline_end.date().isoformat(),
    )
    uplift = 0.0
    if base_avg > 0:
        uplift = round((event_avg - base_avg) / base_avg * 100, 1)

    with get_connection() as conn:
        items_df = pd.read_sql(
            """
            SELECT i.item_id, i.name,
                   SUM(ds.gross_revenue_cents) AS event_rev
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            WHERE ds.sale_date BETWEEN ? AND ?
            GROUP BY i.item_id, i.name
            ORDER BY event_rev DESC
            LIMIT 10
            """,
            conn,
            params=(ev_start, ev_end),
        )

    top_items = items_df.to_dict(orient="records") if not items_df.empty else []

    return {
        "event": event,
        "event_avg_daily_revenue_cents": round(event_avg),
        "baseline_avg_daily_revenue_cents": round(base_avg),
        "uplift_pct": uplift,
        "top_items": top_items,
    }


def get_category_mix_shift(period: str = "30d") -> list:
    bounds = resolve_period(period)
    end = pd.Timestamp(bounds["end"])
    start = pd.Timestamp(bounds["start"])
    prior_end = start - pd.Timedelta(days=1)
    prior_start = prior_end - (end - start)

    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT COALESCE(pc.name, 'Uncategorized') AS name,
                   SUM(CASE WHEN ds.sale_date BETWEEN :cs AND :ce THEN ds.gross_revenue_cents ELSE 0 END) AS cur,
                   SUM(CASE WHEN ds.sale_date BETWEEN :ps AND :pe THEN ds.gross_revenue_cents ELSE 0 END) AS prev
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            LEFT JOIN product_categories pc
              ON i.product_category_id = pc.product_category_id
            WHERE ds.sale_date BETWEEN :ps AND :ce
            GROUP BY COALESCE(pc.name, 'Uncategorized')
            """,
            conn,
            params={
                "cs": start.date().isoformat(),
                "ce": end.date().isoformat(),
                "ps": prior_start.date().isoformat(),
                "pe": prior_end.date().isoformat(),
            },
        )

    if df.empty:
        return []

    cur_total = df["cur"].sum() or 1
    prev_total = df["prev"].sum() or 1
    rows = []
    for _, r in df.iterrows():
        cur_pct = round(r["cur"] / cur_total * 100, 1)
        prev_pct = round(r["prev"] / prev_total * 100, 1)
        rows.append({
            "name": r["name"],
            "current_share_pct": cur_pct,
            "prior_share_pct": prev_pct,
            "share_shift_pct": round(cur_pct - prev_pct, 1),
        })
    return sorted(rows, key=lambda x: abs(x["share_shift_pct"]), reverse=True)


def get_insights_summary(period: str = "30d") -> dict:
    active_events = events_on_date(today())
    wow = get_week_over_week("7d")
    return {
        "period_label": resolve_period(period)["label"],
        "active_events": active_events,
        "wow": wow,
        "calendar_events": get_all_events(),
    }
