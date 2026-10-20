import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
)

app = Flask(__name__)
# Development-only fallback; set SECRET_KEY in the environment for real use.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Profile page sample data — replaced by DB queries in Step 5         #
# ------------------------------------------------------------------ #

PROFILE_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "member_since": "January 2026",
}

PROFILE_STATS = {
    "total_spent": 18240,
    "transaction_count": 42,
    "top_category": "Food",
}

PROFILE_CATEGORIES = [
    {"name": "Food", "total": 5420, "percent": 30},
    {"name": "Bills", "total": 4800, "percent": 26},
    {"name": "Shopping", "total": 3150, "percent": 17},
    {"name": "Transport", "total": 2260, "percent": 12},
    {"name": "Entertainment", "total": 1500, "percent": 8},
    {"name": "Health", "total": 1110, "percent": 6},
]

PROFILE_TRANSACTIONS = [
    {"date": "18 Oct", "description": "Groceries", "category": "Food", "amount": 1240},
    {"date": "16 Oct", "description": "Electricity bill", "category": "Bills", "amount": 2100},
    {"date": "14 Oct", "description": "Metro card top-up", "category": "Transport", "amount": 500},
    {"date": "12 Oct", "description": "Sneakers", "category": "Shopping", "amount": 2450},
    {"date": "09 Oct", "description": "Movie night", "category": "Entertainment", "amount": 650},
    {"date": "07 Oct", "description": "Pharmacy", "category": "Health", "amount": 380},
    {"date": "05 Oct", "description": "Dinner with friends", "category": "Food", "amount": 1150},
    {"date": "02 Oct", "description": "Internet bill", "category": "Bills", "amount": 999},
]


@app.template_filter("inr")
def inr(value):
    """Format a number as rupees with Indian digit grouping: 1234567 -> ₹12,34,567."""
    sign = "-" if value < 0 else ""
    digits = str(int(abs(value)))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}"


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

    user = {**PROFILE_USER, "name": session.get("user_name", PROFILE_USER["name"])}
    return render_template(
        "profile.html",
        user=user,
        stats=PROFILE_STATS,
        categories=PROFILE_CATEGORIES,
        transactions=PROFILE_TRANSACTIONS,
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
