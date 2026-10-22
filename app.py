import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
)
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
# Development-only fallback; set SECRET_KEY in the environment for real use.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")

with app.app_context():
    init_db()
    seed_db()


@app.template_filter("inr")
def inr(value):
    """Format a number as rupees with Indian digit grouping: 1234567.5 -> ₹12,34,567.50."""
    sign = "-" if value < 0 else ""
    whole, _, paise = f"{abs(value):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}.{paise}"


@app.template_filter("short_date")
def short_date(value):
    """Format an ISO date: 2026-10-18 -> 18 Oct."""
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b")


def parse_date_range(args):
    """Read the optional start/end query params as (start, end, error).

    Dates are ISO YYYY-MM-DD strings. On any invalid input both bounds are
    dropped so the page falls back to unfiltered data.
    """
    bounds = []
    for key in ("start", "end"):
        value = args.get(key, "").strip()
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return None, None, "Enter dates as YYYY-MM-DD."
        bounds.append(value or None)

    start, end = bounds
    if start and end and start > end:
        return None, None, "Start date must be on or before end date."
    return start, end, None


def date_presets(today):
    """Return the quick-select ranges as [{label, start, end}].

    "All time" has no bounds. "This month" runs from the 1st to the last day
    of the current month; "Last 3 months" starts on the 1st of the month two
    months back and ends on the same last day.
    """
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    months_back = today.year * 12 + today.month - 1 - 2
    three_months_start = date(months_back // 12, months_back % 12 + 1, 1)
    return [
        {"label": "All time", "start": None, "end": None},
        {
            "label": "This month",
            "start": today.replace(day=1).isoformat(),
            "end": month_end.isoformat(),
        },
        {
            "label": "Last 3 months",
            "start": three_months_start.isoformat(),
            "end": month_end.isoformat(),
        },
    ]


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    def fail(error):
        return render_template("register.html", error=error, name=name, email=email)

    if not name or not email or not password or not confirm_password:
        return fail("All fields are required.")

    local, _, domain = email.partition("@")
    domain_name, _, tld = domain.rpartition(".")
    if not local or "@" in domain or not domain_name or not tld:
        return fail("Enter a valid email address.")

    if len(password) < 8:
        return fail("Password must be at least 8 characters.")

    if password != confirm_password:
        return fail("Passwords do not match.")

    if get_user_by_email(email):
        return fail("An account with that email already exists.")

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return fail("An account with that email already exists.")

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def fail(error):
        return render_template("login.html", error=error, email=email)

    if not email or not password:
        return fail("Email and password are required.")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return fail("Invalid email or password.")

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    start, end, error = parse_date_range(request.args)
    presets = date_presets(date.today())
    matched = next(
        (p for p in presets if (p["start"], p["end"]) == (start, end)), None
    )
    # The date inputs show only for a range no preset covers, after a click
    # on "Custom", or when the entered dates were rejected.
    custom_active = (
        request.args.get("range") == "custom" or error is not None or matched is None
    )
    for preset in presets:
        preset["active"] = preset is matched and not custom_active

    return render_template(
        "profile.html",
        user=user,
        stats=get_summary_stats(user_id, start, end),
        categories=get_category_breakdown(user_id, start, end),
        transactions=get_recent_transactions(
            user_id, start_date=start, end_date=end
        ),
        start=start,
        end=end,
        error=error,
        filtered=bool(start or end),
        presets=presets,
        custom_active=custom_active,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
