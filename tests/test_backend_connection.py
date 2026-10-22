from database import queries


# ------------------------------------------------------------------ #
# Transaction history tests                                           #
# ------------------------------------------------------------------ #

def _insert_expense(user_id, description):
    from database import db

    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, 12.5, "Food", "2099-01-01", description),
        )
        conn.commit()
    finally:
        conn.close()


def test_transactions_demo_user_returns_all_with_keys(demo_user_id):
    rows = queries.get_recent_transactions(demo_user_id)
    assert len(rows) == 8
    for row in rows:
        assert set(row) == {"id", "date", "description", "category", "amount"}
        assert isinstance(row["amount"], float)
        assert len(row["date"]) == 10 and row["date"][4] == "-"


def test_transactions_ordered_newest_first(demo_user_id):
    dates = [t["date"] for t in queries.get_recent_transactions(demo_user_id)]
    assert dates == sorted(dates, reverse=True)


def test_transactions_limit_is_honoured(demo_user_id):
    rows = queries.get_recent_transactions(demo_user_id, limit=3)
    full = queries.get_recent_transactions(demo_user_id)
    assert len(rows) == 3
    assert rows == full[:3]


def test_transactions_empty_for_user_without_expenses(empty_user_id):
    assert queries.get_recent_transactions(empty_user_id) == []


def test_transactions_never_include_other_users(demo_user_id, empty_user_id):
    _insert_expense(empty_user_id, "empty-user-only")
    demo_rows = queries.get_recent_transactions(demo_user_id)
    assert len(demo_rows) == 8
    assert all(r["description"] != "empty-user-only" for r in demo_rows)

    empty_rows = queries.get_recent_transactions(empty_user_id)
    assert [r["description"] for r in empty_rows] == ["empty-user-only"]


# ------------------------------------------------------------------ #
# User and summary stats tests                                        #
# ------------------------------------------------------------------ #

def test_get_user_by_id_valid(demo_user_id):
    from datetime import datetime

    user = queries.get_user_by_id(demo_user_id)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["member_since"] == datetime.now().strftime("%B %Y")


def test_get_user_by_id_unknown(fresh_db):
    assert queries.get_user_by_id(999999) is None


def test_get_user_by_id_no_password_hash(demo_user_id):
    user = queries.get_user_by_id(demo_user_id)
    assert "password_hash" not in user
    assert set(user) == {"name", "email", "member_since"}


def test_get_summary_stats_demo_user(demo_user_id):
    import pytest

    stats = queries.get_summary_stats(demo_user_id)
    assert stats["total_spent"] == pytest.approx(401.5)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_empty_user(empty_user_id):
    assert queries.get_summary_stats(empty_user_id) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_get_summary_stats_ignores_other_users(demo_user_id, empty_user_id):
    import pytest

    from database import db

    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (empty_user_id, 999.0, "Shopping", "2026-01-01", "Other user"),
        )
        conn.commit()
    finally:
        conn.close()

    demo = queries.get_summary_stats(demo_user_id)
    assert demo["total_spent"] == pytest.approx(401.5)
    assert demo["transaction_count"] == 8
    assert demo["top_category"] == "Bills"

    other = queries.get_summary_stats(empty_user_id)
    assert other["total_spent"] == pytest.approx(999.0)
    assert other["transaction_count"] == 1
    assert other["top_category"] == "Shopping"


# ------------------------------------------------------------------ #
# Category breakdown tests                                            #
# ------------------------------------------------------------------ #

def _insert_expenses(user_id, rows):
    from database import db

    conn = db.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date) "
            "VALUES (?, ?, ?, ?)",
            [(user_id, amount, category, "2026-01-15") for category, amount in rows],
        )
        conn.commit()
    finally:
        conn.close()


def test_breakdown_demo_user_shape_and_order(demo_user_id):
    result = queries.get_category_breakdown(demo_user_id)
    assert len(result) == 7
    assert all(set(item) == {"name", "amount", "pct"} for item in result)
    assert result[0]["name"] == "Bills"
    amounts = [item["amount"] for item in result]
    assert amounts == sorted(amounts, reverse=True)


def test_breakdown_demo_user_amounts(demo_user_id):
    import pytest

    result = queries.get_category_breakdown(demo_user_id)
    expected = {
        "Bills": 120.00,
        "Shopping": 80.25,
        "Food": 74.25,
        "Entertainment": 60.00,
        "Health": 35.00,
        "Other": 20.00,
        "Transport": 12.00,
    }
    assert {item["name"]: item["amount"] for item in result} == pytest.approx(expected)


def test_breakdown_pcts_are_ints_summing_to_100(demo_user_id):
    result = queries.get_category_breakdown(demo_user_id)
    assert all(isinstance(item["pct"], int) for item in result)
    assert sum(item["pct"] for item in result) == 100


def test_breakdown_rounding_remainder_goes_to_largest(empty_user_id):
    _insert_expenses(
        empty_user_id, [("Food", 10.00), ("Bills", 10.00), ("Travel", 10.00)]
    )
    result = queries.get_category_breakdown(empty_user_id)
    assert [item["pct"] for item in result] == [34, 33, 33]
    assert sum(item["pct"] for item in result) == 100
    assert result[0]["name"] == "Bills"


def test_breakdown_negative_remainder_taken_from_largest(empty_user_id):
    # 33 + 4 x 17 = 101 after naive rounding, so the largest gives back 1.
    _insert_expenses(
        empty_user_id,
        [("A", 2.0), ("B", 1.0), ("C", 1.0), ("D", 1.0), ("E", 1.0)],
    )
    result = queries.get_category_breakdown(empty_user_id)
    assert [item["pct"] for item in result] == [32, 17, 17, 17, 17]
    assert sum(item["pct"] for item in result) == 100


def test_breakdown_empty_user_returns_empty_list(empty_user_id):
    assert queries.get_category_breakdown(empty_user_id) == []


def test_breakdown_ignores_other_users_expenses(demo_user_id, empty_user_id):
    _insert_expenses(empty_user_id, [("Travel", 500.00)])
    demo = queries.get_category_breakdown(demo_user_id)
    other = queries.get_category_breakdown(empty_user_id)
    assert "Travel" not in [item["name"] for item in demo]
    assert other == [{"name": "Travel", "amount": 500.00, "pct": 100}]

# ------------------------------------------------------------------ #
# Route tests                                                         #
# ------------------------------------------------------------------ #

def _log_in(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_profile_redirects_when_logged_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_shows_seed_user_data(client):
    _log_in(client, "demo@spendly.com", "demo123")
    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "₹401.50" in html
    assert "Bills" in html
    assert "PROFILE_" not in html


def test_profile_lists_eight_transactions_newest_first(client):
    _log_in(client, "demo@spendly.com", "demo123")
    html = client.get("/profile").get_data(as_text=True)

    assert html.count('class="txn-date"') == 8
    # Seeded descriptions, newest date first (day 25 down to day 2).
    order = ["Dinner out", "Gift", "Shoes", "Concert tickets", "Pharmacy",
             "Electricity bill", "Bus pass top-up", "Groceries"]
    positions = [html.index(f'class="txn-desc">{name}') for name in order]
    assert positions == sorted(positions)


def test_profile_shows_all_seven_categories(client):
    _log_in(client, "demo@spendly.com", "demo123")
    html = client.get("/profile").get_data(as_text=True)

    assert html.count('class="breakdown-row"') == 7


def test_profile_for_user_without_expenses(client, empty_user_id):
    _log_in(client, "empty@example.com", "password123")
    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Empty User" in html
    assert "₹0.00" in html
    assert "No transactions yet." in html
    assert "No spending to break down yet." in html


def test_profile_redirects_when_session_user_is_gone(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 999999
        sess["user_name"] = "Ghost"
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
