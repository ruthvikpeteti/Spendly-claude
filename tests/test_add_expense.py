import pytest

from database import db
from tests.conftest import login

CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]

VALID = {
    "amount": "50.00",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Lunch",
}


def expenses_for(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def count_expenses():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def authed(client, empty_user_id):
    login(client, empty_user_id, "Empty User")
    return client


# ------------------------------------------------------------------ #
# create_expense                                                      #
# ------------------------------------------------------------------ #

def test_create_expense_inserts_row(empty_user_id):
    new_id = db.create_expense(empty_user_id, 50.0, "Food", "2026-03-20", "Lunch")
    rows = expenses_for(empty_user_id)
    assert len(rows) == 1
    assert rows[0]["id"] == new_id
    assert rows[0]["amount"] == 50.0
    assert rows[0]["category"] == "Food"
    assert rows[0]["date"] == "2026-03-20"
    assert rows[0]["description"] == "Lunch"


def test_create_expense_none_description_is_null(empty_user_id):
    db.create_expense(empty_user_id, 10.0, "Bills", "2026-03-20", None)
    assert expenses_for(empty_user_id)[0]["description"] is None


# ------------------------------------------------------------------ #
# Access control                                                      #
# ------------------------------------------------------------------ #

def test_get_unauthenticated_redirects_to_login(client):
    response = client.get("/expenses/add")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_post_unauthenticated_redirects_and_inserts_nothing(client):
    before = count_expenses()
    response = client.post("/expenses/add", data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert count_expenses() == before


# ------------------------------------------------------------------ #
# GET                                                                 #
# ------------------------------------------------------------------ #

def test_get_renders_form_with_all_categories(authed):
    response = authed.get("/expenses/add")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<form" in html and 'method="POST"' in html
    for category in CATEGORIES:
        assert f'<option value="{category}"' in html
    assert html.count("<option") == len(CATEGORIES)
    for field in ("amount", "category", "date", "description"):
        assert f'name="{field}"' in html


# ------------------------------------------------------------------ #
# POST — success                                                      #
# ------------------------------------------------------------------ #

def test_post_valid_inserts_and_redirects_to_profile(authed, empty_user_id):
    response = authed.post("/expenses/add", data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    rows = expenses_for(empty_user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == 50.0
    assert rows[0]["description"] == "Lunch"


def test_post_without_description_stores_null(authed, empty_user_id):
    response = authed.post("/expenses/add", data={**VALID, "description": "  "})
    assert response.status_code == 302
    assert expenses_for(empty_user_id)[0]["description"] is None


def test_new_expense_appears_on_profile(authed):
    authed.post("/expenses/add", data={**VALID, "description": "UniqueLunchXYZ"})
    html = authed.get("/profile").get_data(as_text=True)
    assert "UniqueLunchXYZ" in html
    assert "₹50.00" in html


def test_success_alert_shows_expense_details_once(authed):
    response = authed.post(
        "/expenses/add",
        data={**VALID, "amount": "1250.5", "description": "Team lunch"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert 'class="flash-success"' in html
    assert "Expense added: ₹1,250.50 · Food · 20 Mar · Team lunch" in html

    again = authed.get("/profile").get_data(as_text=True)
    assert "flash-success" not in again


def test_success_alert_omits_blank_description(authed):
    html = authed.post(
        "/expenses/add", data={**VALID, "description": ""}, follow_redirects=True
    ).get_data(as_text=True)
    assert "Expense added: ₹50.00 · Food · 20 Mar<" in html


def test_no_alert_on_validation_error(authed):
    html = authed.post(
        "/expenses/add", data={**VALID, "amount": "0"}
    ).get_data(as_text=True)
    assert "flash-success" not in html
    assert "flash-success" not in authed.get("/profile").get_data(as_text=True)


# ------------------------------------------------------------------ #
# POST — validation errors                                            #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"amount": "nan"},
        {"amount": "inf"},
        {"category": "Groceries"},
        {"category": ""},
        {"date": ""},
        {"date": "not-a-date"},
        {"date": "2026-13-45"},
        {"description": "x" * 201},
    ],
)
def test_post_invalid_rerenders_with_error(authed, empty_user_id, overrides):
    response = authed.post("/expenses/add", data={**VALID, **overrides})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="auth-error"' in html
    assert expenses_for(empty_user_id) == []


def test_post_invalid_keeps_submitted_values(authed):
    response = authed.post(
        "/expenses/add",
        data={**VALID, "amount": "0", "category": "Health", "description": "Keep me"},
    )
    html = response.get_data(as_text=True)
    assert 'value="0"' in html
    assert '<option value="Health" selected>' in html
    assert 'value="2026-03-20"' in html
    assert 'value="Keep me"' in html


# ------------------------------------------------------------------ #
# POST — security                                                     #
# ------------------------------------------------------------------ #

def test_forged_user_id_is_ignored(authed, empty_user_id, demo_user_id):
    authed.post("/expenses/add", data={**VALID, "user_id": str(demo_user_id)})
    assert len(expenses_for(empty_user_id)) == 1
    assert all(r["description"] != "Lunch" for r in expenses_for(demo_user_id))


def test_description_is_html_escaped_on_profile(authed):
    authed.post(
        "/expenses/add",
        data={**VALID, "description": "<script>alert(1)</script>"},
    )
    html = authed.get("/profile").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ------------------------------------------------------------------ #
# Navigation                                                          #
# ------------------------------------------------------------------ #

def test_navbar_and_profile_link_when_logged_in(authed):
    html = authed.get("/profile").get_data(as_text=True)
    assert html.count('href="/expenses/add"') == 2


def test_navbar_hides_link_when_logged_out(client):
    html = client.get("/").get_data(as_text=True)
    assert "/expenses/add" not in html


def test_edit_and_delete_stubs_untouched(client):
    assert b"Step 8" in client.get("/expenses/1/edit").data
    assert b"Step 9" in client.get("/expenses/1/delete").data
