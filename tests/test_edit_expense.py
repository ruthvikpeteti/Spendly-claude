import pytest

from database import db, queries
from tests.conftest import login

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

VALID = {
    "amount": "99.50",
    "category": "Bills",
    "date": "2026-04-02",
    "description": "Updated",
}


def fetch_expense(expense_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture
def owner_id(empty_user_id):
    return empty_user_id


@pytest.fixture
def other_user_id(fresh_db):
    return db.create_user("Other User", "other@example.com", "password123")


@pytest.fixture
def expense_id(owner_id):
    return db.create_expense(owner_id, 50.0, "Food", "2026-03-20", "Lunch")


@pytest.fixture
def others_expense_id(other_user_id):
    return db.create_expense(other_user_id, 70.0, "Health", "2026-03-21", "Secret")


@pytest.fixture
def authed(client, owner_id):
    login(client, owner_id, "Empty User")
    return client


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


# ------------------------------------------------------------------ #
# get_expense_by_id                                                   #
# ------------------------------------------------------------------ #


def test_get_expense_by_id_returns_own_expense(owner_id, expense_id):
    expense = queries.get_expense_by_id(expense_id, owner_id)
    assert expense == {
        "id": expense_id,
        "amount": 50.0,
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }


def test_get_expense_by_id_wrong_user_returns_none(other_user_id, expense_id):
    assert queries.get_expense_by_id(expense_id, other_user_id) is None


def test_get_expense_by_id_missing_returns_none(owner_id):
    assert queries.get_expense_by_id(9999, owner_id) is None


# ------------------------------------------------------------------ #
# update_expense                                                      #
# ------------------------------------------------------------------ #


def test_update_expense_changes_row(owner_id, expense_id):
    changed = db.update_expense(expense_id, owner_id, 99.0, "Bills", "2026-04-02", None)
    row = fetch_expense(expense_id)
    assert changed is True
    assert row["amount"] == 99.0
    assert row["category"] == "Bills"
    assert row["date"] == "2026-04-02"
    assert row["description"] is None
    assert row["user_id"] == owner_id


def test_update_expense_wrong_user_changes_nothing(other_user_id, expense_id):
    changed = db.update_expense(
        expense_id, other_user_id, 99.0, "Bills", "2026-04-02", "Hijacked"
    )
    row = fetch_expense(expense_id)
    assert changed is False
    assert row["amount"] == 50.0
    assert row["description"] == "Lunch"


def test_update_expense_missing_id_returns_false(owner_id):
    assert db.update_expense(9999, owner_id, 1.0, "Food", "2026-04-02", None) is False


# ------------------------------------------------------------------ #
# Access control                                                      #
# ------------------------------------------------------------------ #


def test_get_unauthenticated_redirects_to_login(client, expense_id):
    response = client.get(edit_url(expense_id))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_post_unauthenticated_redirects_and_changes_nothing(client, expense_id):
    response = client.post(edit_url(expense_id), data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert fetch_expense(expense_id)["amount"] == 50.0


def test_get_missing_expense_returns_404(authed):
    assert authed.get(edit_url(9999)).status_code == 404


def test_post_missing_expense_returns_404(authed):
    assert authed.post(edit_url(9999), data=VALID).status_code == 404


def test_get_other_users_expense_returns_404(authed, others_expense_id):
    assert authed.get(edit_url(others_expense_id)).status_code == 404


def test_post_other_users_expense_returns_404_and_changes_nothing(
    authed, others_expense_id
):
    response = authed.post(edit_url(others_expense_id), data=VALID)
    row = fetch_expense(others_expense_id)
    assert response.status_code == 404
    assert row["amount"] == 70.0
    assert row["description"] == "Secret"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #


def test_get_prefills_current_values(authed, expense_id):
    response = authed.get(edit_url(expense_id))
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<form method="POST"' in html
    assert f'action="{edit_url(expense_id)}"' in html
    assert 'value="50.0"' in html
    assert 'value="2026-03-20"' in html
    assert 'value="Lunch"' in html


def test_get_preselects_current_category(authed, expense_id):
    html = authed.get(edit_url(expense_id)).get_data(as_text=True)
    for category in CATEGORIES:
        assert f'<option value="{category}"' in html
    assert '<option value="Food" selected>' in html
    assert html.count(" selected>") == 1


# ------------------------------------------------------------------ #
# POST success                                                        #
# ------------------------------------------------------------------ #


def test_post_valid_updates_row_and_redirects_to_profile(authed, expense_id):
    response = authed.post(edit_url(expense_id), data=VALID)
    row = fetch_expense(expense_id)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    assert row["amount"] == 99.5
    assert row["category"] == "Bills"
    assert row["date"] == "2026-04-02"
    assert row["description"] == "Updated"


def test_post_blank_description_stores_null(authed, expense_id):
    response = authed.post(edit_url(expense_id), data={**VALID, "description": "   "})
    assert response.status_code == 302
    assert fetch_expense(expense_id)["description"] is None


def test_post_does_not_change_owner(authed, owner_id, other_user_id, expense_id):
    authed.post(edit_url(expense_id), data={**VALID, "user_id": other_user_id})
    assert fetch_expense(expense_id)["user_id"] == owner_id


def test_post_success_shows_flash_on_profile(authed, expense_id):
    response = authed.post(edit_url(expense_id), data=VALID, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Expense updated" in html
    assert "₹99.50" in html


# ------------------------------------------------------------------ #
# POST validation                                                     #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"amount": "nan"},
        {"category": "Nonsense"},
        {"category": ""},
        {"date": "not-a-date"},
        {"date": "2026-13-45"},
        {"date": ""},
        {"description": "x" * 201},
    ],
)
def test_post_invalid_rerenders_with_error_and_changes_nothing(
    authed, expense_id, overrides
):
    response = authed.post(edit_url(expense_id), data={**VALID, **overrides})
    row = fetch_expense(expense_id)
    assert response.status_code == 200
    assert 'role="alert"' in response.get_data(as_text=True)
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_post_invalid_keeps_submitted_values(authed, expense_id):
    response = authed.post(
        edit_url(expense_id), data={**VALID, "amount": "0", "description": "Mine"}
    )
    html = response.get_data(as_text=True)
    assert 'value="Mine"' in html
    assert 'value="2026-04-02"' in html
    assert '<option value="Bills" selected>' in html


# ------------------------------------------------------------------ #
# Profile page link                                                   #
# ------------------------------------------------------------------ #


def test_profile_rows_link_to_edit_page(authed, expense_id):
    html = authed.get("/profile").get_data(as_text=True)
    assert f'href="{edit_url(expense_id)}"' in html
    assert ">Actions</th>" in html


def test_profile_get_recent_transactions_includes_id(owner_id, expense_id):
    rows = queries.get_recent_transactions(owner_id)
    assert [row["id"] for row in rows] == [expense_id]
