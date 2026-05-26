"""
Aggregation functions that power the three dashboard pages.

All functions return plain Python dicts or lists — no pandas objects
are exposed to routes, so templates can iterate without extra imports.
"""

from datetime import date, timedelta

import pandas as pd

from app.database import get_connection
from app.analysis.periods import resolve_period


def _period_bounds(period: str) -> tuple[str, str, int]:
    info = resolve_period(period)
    return info["start"], info["end"], info["day_count"]


# ---------------------------------------------------------------------------
# Sales dashboard
# ---------------------------------------------------------------------------

def get_sales_stats(period: str = "week", category_id: str = None) -> dict:
    """
    Returns aggregate KPIs and a daily revenue series for the Sales dashboard.

    Keys: total_revenue_cents, units_sold, active_items, daily_labels, daily_values
    """
    start, end, _ = _period_bounds(period)

    with get_connection() as conn:
        params: dict = {"start": start, "end": end}

        cat_join = ""
        cat_where = ""
        if category_id:
            cat_join = "JOIN items i ON ds.item_id = i.item_id"
            cat_where = "AND i.category_id = :category_id"
            params["category_id"] = category_id

        sales_df = pd.read_sql(
            f"""
            SELECT ds.sale_date,
                   SUM(ds.units_sold)          AS units_sold,
                   SUM(ds.gross_revenue_cents)  AS revenue_cents
            FROM daily_sales ds
            {cat_join}
            WHERE ds.sale_date BETWEEN :start AND :end
            {cat_where}
            GROUP BY ds.sale_date
            ORDER BY ds.sale_date
            """,
            conn,
            params=params,
        )

        active_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM items WHERE is_active = 1"
        ).fetchone()["cnt"]

    total_revenue = int(sales_df["revenue_cents"].sum()) if not sales_df.empty else 0
    total_units = int(sales_df["units_sold"].sum()) if not sales_df.empty else 0

    daily_labels = sales_df["sale_date"].tolist()
    daily_values = [int(v) for v in sales_df["revenue_cents"].tolist()]

    return {
        "total_revenue_cents": total_revenue,
        "units_sold": total_units,
        "active_items": active_count,
        "daily_labels": daily_labels,
        "daily_values": daily_values,
    }


def get_sales_by_category(period: str = "week", category_id: str = None) -> list:
    """
    Returns revenue by category for the period, sorted descending by revenue.

    Each row: {category_id, name, revenue_cents, units_sold}
    """
    start, end, _ = _period_bounds(period)

    cat_where = ""
    params: dict = {"start": start, "end": end}
    if category_id:
        cat_where = "AND i.category_id = :category_id"
        params["category_id"] = category_id

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                COALESCE(c.category_id, 'uncategorized') AS category_id,
                COALESCE(c.name, 'Uncategorized')        AS name,
                SUM(ds.gross_revenue_cents)               AS revenue_cents,
                SUM(ds.units_sold)                        AS units_sold
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE ds.sale_date BETWEEN :start AND :end
            {cat_where}
            GROUP BY COALESCE(c.category_id, 'uncategorized'), COALESCE(c.name, 'Uncategorized')
            ORDER BY revenue_cents DESC
            """,
            conn,
            params=params,
        )

    if df.empty:
        return []
    df["revenue_cents"] = df["revenue_cents"].fillna(0).astype(int)
    df["units_sold"] = df["units_sold"].fillna(0).astype(int)
    return df.to_dict(orient="records")


def get_top_products(period: str = "week", top_n: int = 10, category_id: str = None) -> list:
    """
    Returns the top-n items by revenue for the period.

    Each row: {item_id, name, units_sold, revenue_cents}
    """
    start, end, _ = _period_bounds(period)

    cat_where = ""
    params: dict = {"start": start, "end": end, "top_n": top_n}
    if category_id:
        cat_where = "AND i.category_id = :category_id"
        params["category_id"] = category_id

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                i.item_id,
                i.name,
                SUM(ds.units_sold)          AS units_sold,
                SUM(ds.gross_revenue_cents)  AS revenue_cents
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            WHERE ds.sale_date BETWEEN :start AND :end
            {cat_where}
            GROUP BY i.item_id, i.name
            ORDER BY revenue_cents DESC
            LIMIT :top_n
            """,
            conn,
            params=params,
        )

    if df.empty:
        return []
    df["revenue_cents"] = df["revenue_cents"].fillna(0).astype(int)
    df["units_sold"] = df["units_sold"].fillna(0).astype(int)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Inventory dashboard
# ---------------------------------------------------------------------------

def get_inventory_stats(period: str = "week") -> dict:
    """
    Returns KPIs for the Inventory Turnover dashboard.

    Keys: turnover_rate, days_on_hand, low_stock_count, total_stock_units
    """
    start, end, period_days = _period_bounds(period)

    with get_connection() as conn:
        # Latest snapshot quantity per item
        stock_df = pd.read_sql(
            """
            SELECT item_id, quantity
            FROM stock_snapshots
            WHERE id IN (
                SELECT MAX(id) FROM stock_snapshots GROUP BY item_id
            )
            """,
            conn,
        )

        # Units sold for the period
        sales_df = pd.read_sql(
            """
            SELECT item_id, SUM(units_sold) AS units_sold
            FROM daily_sales
            WHERE sale_date BETWEEN :start AND :end
            GROUP BY item_id
            """,
            conn,
            params={"start": start, "end": end},
        )

    total_stock = int(stock_df["quantity"].sum()) if not stock_df.empty else 0
    avg_stock = stock_df["quantity"].mean() if not stock_df.empty else 0
    total_units_sold = int(sales_df["units_sold"].sum()) if not sales_df.empty else 0

    if avg_stock > 0 and period_days > 0:
        daily_sales_rate = total_units_sold / period_days
        turnover_rate = round(total_units_sold / avg_stock, 2)
        days_on_hand = round(avg_stock / daily_sales_rate, 1) if daily_sales_rate > 0 else None
    else:
        turnover_rate = 0.0
        days_on_hand = None

    low_stock_count = int((stock_df["quantity"] < 10).sum()) if not stock_df.empty else 0

    return {
        "turnover_rate": turnover_rate,
        "days_on_hand": days_on_hand,
        "low_stock_count": low_stock_count,
        "total_stock_units": total_stock,
    }


def get_stock_by_category() -> list:
    """
    Returns total current stock per category (latest snapshot per item).

    Each row: {category_id, name, total_stock}
    """
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT
                COALESCE(c.category_id, 'uncategorized') AS category_id,
                COALESCE(c.name, 'Uncategorized')        AS name,
                SUM(ss.quantity)                          AS total_stock
            FROM stock_snapshots ss
            JOIN items i ON ss.item_id = i.item_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE ss.id IN (
                SELECT MAX(id) FROM stock_snapshots GROUP BY item_id
            )
            GROUP BY COALESCE(c.category_id, 'uncategorized'), COALESCE(c.name, 'Uncategorized')
            ORDER BY total_stock DESC
            """,
            conn,
        )

    if df.empty:
        return []
    df["total_stock"] = df["total_stock"].fillna(0).astype(int)
    return df.to_dict(orient="records")


def get_turnover_by_category(period: str = "week") -> list:
    """
    Returns turnover rate per category for the period.

    Each row: {category_id, name, units_sold, avg_stock, turnover_rate}
    """
    start, end, _ = _period_bounds(period)

    with get_connection() as conn:
        stock_df = pd.read_sql(
            """
            SELECT
                i.item_id,
                COALESCE(c.category_id, 'uncategorized') AS category_id,
                COALESCE(c.name, 'Uncategorized')        AS name,
                ss.quantity
            FROM stock_snapshots ss
            JOIN items i ON ss.item_id = i.item_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE ss.id IN (
                SELECT MAX(id) FROM stock_snapshots GROUP BY item_id
            )
            """,
            conn,
        )

        sales_df = pd.read_sql(
            """
            SELECT item_id, SUM(units_sold) AS units_sold
            FROM daily_sales
            WHERE sale_date BETWEEN :start AND :end
            GROUP BY item_id
            """,
            conn,
            params={"start": start, "end": end},
        )

    if stock_df.empty:
        return []

    merged = stock_df.merge(sales_df, on="item_id", how="left")
    merged["units_sold"] = merged["units_sold"].fillna(0)

    grouped = merged.groupby(["category_id", "name"]).agg(
        units_sold=("units_sold", "sum"),
        avg_stock=("quantity", "mean"),
    ).reset_index()

    grouped["turnover_rate"] = grouped.apply(
        lambda row: round(row["units_sold"] / row["avg_stock"], 2) if row["avg_stock"] > 0 else 0.0,
        axis=1,
    )
    grouped = grouped.sort_values("turnover_rate", ascending=False)
    grouped["units_sold"] = grouped["units_sold"].astype(int)
    grouped["avg_stock"] = grouped["avg_stock"].round(1)
    return grouped.to_dict(orient="records")


def get_low_stock_items(threshold: int = 10) -> list:
    """
    Returns items whose latest snapshot quantity is below `threshold`.

    Each row: {item_id, name, quantity, category_name}
    """
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT
                i.item_id,
                i.name,
                ss.quantity,
                COALESCE(c.name, 'Uncategorized') AS category_name
            FROM stock_snapshots ss
            JOIN items i ON ss.item_id = i.item_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE ss.id IN (
                SELECT MAX(id) FROM stock_snapshots GROUP BY item_id
            )
              AND ss.quantity < :threshold
            ORDER BY ss.quantity ASC
            """,
            conn,
            params={"threshold": threshold},
        )

    if df.empty:
        return []
    df["quantity"] = df["quantity"].astype(int)
    return df.to_dict(orient="records")


def get_stock_chart_data(top_n: int = 20) -> dict:
    """
    Returns labels and quantities for the top-n items by current stock.

    Keys: labels (list[str]), values (list[int])
    """
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT i.name, ss.quantity
            FROM stock_snapshots ss
            JOIN items i ON ss.item_id = i.item_id
            WHERE ss.id IN (
                SELECT MAX(id) FROM stock_snapshots GROUP BY item_id
            )
            ORDER BY ss.quantity DESC
            LIMIT :top_n
            """,
            conn,
            params={"top_n": top_n},
        )

    if df.empty:
        return {"labels": [], "values": []}
    return {
        "labels": df["name"].tolist(),
        "values": [int(v) for v in df["quantity"].tolist()],
    }


# ---------------------------------------------------------------------------
# Profit dashboard
# ---------------------------------------------------------------------------

def get_profit_stats(period: str = "week", category_id: str = None) -> dict:
    """
    Returns KPIs for the Profit dashboard.

    Keys: gross_profit_cents, profit_margin_pct, total_costs_cents,
          no_cost_count, daily_labels, daily_values
    """
    start, end, _ = _period_bounds(period)

    cat_where = ""
    params: dict = {"start": start, "end": end}
    if category_id:
        cat_where = "AND i.category_id = :category_id"
        params["category_id"] = category_id

    with get_connection() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                ds.sale_date,
                SUM(ds.units_sold)                                      AS units_sold,
                SUM(ds.gross_revenue_cents)                             AS revenue_cents,
                SUM(
                    CASE WHEN i.cost_cents IS NOT NULL
                    THEN ds.units_sold * i.cost_cents ELSE 0 END
                )                                                        AS cost_cents,
                SUM(
                    CASE WHEN i.cost_cents IS NOT NULL
                    THEN ds.units_sold * (i.price_cents - i.cost_cents) ELSE 0 END
                )                                                        AS profit_cents
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            WHERE ds.sale_date BETWEEN :start AND :end
            {cat_where}
            GROUP BY ds.sale_date
            ORDER BY ds.sale_date
            """,
            conn,
            params=params,
        )

        no_cost_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM items WHERE cost_cents IS NULL AND is_active = 1"
        ).fetchone()["cnt"]

    if df.empty:
        return {
            "gross_profit_cents": 0,
            "profit_margin_pct": 0.0,
            "total_costs_cents": 0,
            "no_cost_count": no_cost_count,
            "daily_labels": [],
            "daily_values": [],
        }

    gross_profit = int(df["profit_cents"].sum())
    total_costs = int(df["cost_cents"].sum())
    total_revenue = int(df["revenue_cents"].sum())
    profit_margin_pct = round(gross_profit / total_revenue * 100, 1) if total_revenue > 0 else 0.0

    return {
        "gross_profit_cents": gross_profit,
        "profit_margin_pct": profit_margin_pct,
        "total_costs_cents": total_costs,
        "no_cost_count": no_cost_count,
        "daily_labels": df["sale_date"].tolist(),
        "daily_values": [int(v) for v in df["profit_cents"].tolist()],
    }


def get_profit_by_category(period: str = "week") -> list:
    """
    Returns revenue, cost, and margin per category for the period.

    Each row: {category_id, name, revenue_cents, cost_cents, margin_pct}
    """
    start, end, _ = _period_bounds(period)

    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT
                COALESCE(c.category_id, 'uncategorized') AS category_id,
                COALESCE(c.name, 'Uncategorized')        AS name,
                SUM(ds.gross_revenue_cents)               AS revenue_cents,
                SUM(
                    CASE WHEN i.cost_cents IS NOT NULL
                    THEN ds.units_sold * i.cost_cents ELSE 0 END
                )                                         AS cost_cents
            FROM daily_sales ds
            JOIN items i ON ds.item_id = i.item_id
            LEFT JOIN categories c ON i.category_id = c.category_id
            WHERE ds.sale_date BETWEEN :start AND :end
            GROUP BY COALESCE(c.category_id, 'uncategorized'), COALESCE(c.name, 'Uncategorized')
            ORDER BY revenue_cents DESC
            """,
            conn,
            params={"start": start, "end": end},
        )

    if df.empty:
        return []

    df["revenue_cents"] = df["revenue_cents"].fillna(0).astype(int)
    df["cost_cents"] = df["cost_cents"].fillna(0).astype(int)
    df["gross_profit_cents"] = df["revenue_cents"] - df["cost_cents"]
    df["margin_pct"] = df.apply(
        lambda row: round(row["gross_profit_cents"] / row["revenue_cents"] * 100, 1)
        if row["revenue_cents"] > 0 else 0.0,
        axis=1,
    )
    return df.to_dict(orient="records")


def get_weekly_profit(weeks: int = 8) -> list:
    """
    Returns week-by-week gross profit for the past `weeks` weeks.

    Each row: {week_start, gross_profit_cents}
    """
    today = date.today()
    rows = []
    for i in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT SUM(
                    CASE WHEN i.cost_cents IS NOT NULL
                    THEN ds.units_sold * (i.price_cents - i.cost_cents) ELSE 0 END
                ) AS profit_cents
                FROM daily_sales ds
                JOIN items i ON ds.item_id = i.item_id
                WHERE ds.sale_date BETWEEN ? AND ?
                """,
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchone()
        profit = int(result["profit_cents"]) if result and result["profit_cents"] else 0
        rows.append({"week_start": week_start.isoformat(), "gross_profit_cents": profit})
    return rows


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_all_categories() -> list:
    """Returns all category rows for filter dropdowns."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT category_id, name FROM categories ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]
