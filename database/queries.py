"""Read-only query helpers for the profile page. No Flask imports."""

from database.db import get_db
from datetime import datetime


def _date_clause(start_date, end_date):
    """Return (sql_fragment, params) bounding expenses.date, inclusive.

    The fragment is built from fixed strings only; the dates travel as
    parameters. Either bound may be None.
    """
    clause = ""
    params = []
    if start_date:
        clause += " AND date >= ?"
        params.append(start_date)
    if end_date:
        clause += " AND date <= ?"
        params.append(end_date)
    return clause, params


# ------------------------------------------------------------------ #
# User and summary stats                                              #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    """Return {name, email, member_since} for user_id, or None if unknown."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created.strftime("%B %Y"),
    }


def get_summary_stats(user_id, start_date=None, end_date=None):
    """Return {total_spent, transaction_count, top_category} for user_id.

    start_date / end_date are optional inclusive ISO bounds.
    """
    clause, params = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?" + clause,
            (user_id, *params),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause +
            " GROUP BY category ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            (user_id, *params),
        ).fetchone()
    finally:
        conn.close()

    if totals["cnt"] == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    return {
        "total_spent": round(totals["total"], 2),
        "transaction_count": totals["cnt"],
        "top_category": top["category"],
    }


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def get_recent_transactions(user_id, limit=10, start_date=None, end_date=None):
    """Return the user's newest expenses as a list of dicts.

    start_date / end_date are optional inclusive ISO bounds.
    """
    clause, params = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + clause +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *params, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id, start_date=None, end_date=None):
    """Return [{name, amount, pct}] ordered by amount descending.

    start_date / end_date are optional inclusive ISO bounds.

    pct values are whole numbers that always sum to exactly 100; any
    rounding remainder is absorbed by the largest category.
    """
    clause, params = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category "
            "ORDER BY SUM(amount) DESC, category ASC",
            (user_id, *params),
        ).fetchall()
    finally:
        conn.close()

    grand_total = sum(row["total"] for row in rows)
    breakdown = [
        {
            "name": row["category"],
            "amount": round(float(row["total"]), 2),
            "pct": int(round(row["total"] / grand_total * 100))
            if grand_total > 0 else 0,
        }
        for row in rows
    ]
    if breakdown and grand_total > 0:
        breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
