"""Tests for Step 7: Add Expense (GET/POST /expenses/add).

Written from .claude/specs/07-add-expense.md. Fixtures (client, demo_user_id,
empty_user_id) and the login() helper come from tests/conftest.py.
"""
import re
import sqlite3
from datetime import date
from urllib.parse import urlparse

import pytest
from flask import url_for

from app import app as flask_app
from database import db
from conftest import login

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

VALID_FORM = {
    "amount": "50.0",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Lunch",
}


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def url(endpoint, **values):
    """Resolve an endpoint to its URL path without hardcoding it."""
    with flask_app.test_request_context():
        return url_for(endpoint, **values)


def path_of(response):
    """Path component of a redirect response's Location header."""
    return urlparse(response.headers["Location"]).path


def expenses_for(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def expense_count():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()["n"]
    finally:
        conn.close()


def has_error(response):
    """True if the page shows an element whose class marks it as an error."""
    html = response.get_data(as_text=True)
    return re.search(r'class="[^"]*error[^"]*"', html, re.IGNORECASE) is not None


def form_with(**overrides):
    data = dict(VALID_FORM)
    data.update(overrides)
    return data


def select_option_labels(html):
    select = re.search(
        r'<select[^>]*name="category"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    assert select, "Expected a <select name=\"category\"> in the form"
    return [
        label.strip()
        for label in re.findall(r"<option[^>]*>([^<]*)</option>", select.group(1))
    ]


def input_tag(html, name):
    tag = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(name), html)
    assert tag, f"Expected an <input name=\"{name}\"> in the form"
    return tag.group(0)


@pytest.fixture
def demo_client(client, demo_user_id):
    login(client, demo_user_id, "Demo User")
    return client


@pytest.fixture
def empty_client(client, empty_user_id):
    login(client, empty_user_id, "Empty User")
    return client


# ------------------------------------------------------------------ #
# Unit tests: create_expense                                          #
# ------------------------------------------------------------------ #

class TestCreateExpense:
    def test_create_expense_valid_data_inserts_row(self, empty_user_id):
        db.create_expense(empty_user_id, 50.0, "Food", "2026-03-20", "Lunch")

        rows = expenses_for(empty_user_id)
        assert len(rows) == 1, "Expected exactly one stored expense"
        row = rows[0]
        assert row["user_id"] == empty_user_id
        assert row["amount"] == pytest.approx(50.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"
        assert row["created_at"], "created_at should be populated"

    def test_create_expense_none_description_stores_null(self, empty_user_id):
        db.create_expense(empty_user_id, 12.5, "Transport", "2026-03-21", None)

        rows = expenses_for(empty_user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None, "description should be NULL"

    def test_create_expense_does_not_touch_other_users(
        self, empty_user_id, demo_user_id
    ):
        before = len(expenses_for(demo_user_id))
        db.create_expense(empty_user_id, 5.0, "Other", "2026-03-22", "x")

        assert len(expenses_for(demo_user_id)) == before

    def test_create_expense_multiple_calls_insert_multiple_rows(self, empty_user_id):
        db.create_expense(empty_user_id, 1.0, "Food", "2026-03-01", "a")
        db.create_expense(empty_user_id, 2.0, "Bills", "2026-03-02", "b")

        assert len(expenses_for(empty_user_id)) == 2

    def test_create_expense_unknown_user_violates_foreign_key(self, fresh_db):
        before = expense_count()

        with pytest.raises(sqlite3.IntegrityError):
            db.create_expense(999999, 5.0, "Food", "2026-03-20", "ghost")

        assert expense_count() == before, "Orphan expense must not be stored"

    def test_create_expense_sql_metacharacters_stored_literally(self, empty_user_id):
        evil = "x'); DROP TABLE expenses;--"
        db.create_expense(empty_user_id, 5.0, "Food", "2026-03-20", evil)

        rows = expenses_for(empty_user_id)
        assert [r["description"] for r in rows] == [evil]


# ------------------------------------------------------------------ #
# GET /expenses/add                                                   #
# ------------------------------------------------------------------ #

class TestAddExpenseGet:
    def test_get_logged_out_redirects_to_login(self, client):
        response = client.get(url("add_expense"))

        assert response.status_code == 302
        assert path_of(response) == url("login")

    def test_get_logged_in_returns_200(self, demo_client):
        response = demo_client.get(url("add_expense"))

        assert response.status_code == 200

    def test_get_form_posts_to_add_expense(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        form = re.search(r"<form[^>]*>", html)
        assert form, "Expected a <form> on the page"
        assert re.search(r'method="post"', form.group(0), re.IGNORECASE), (
            "Form must use method POST"
        )
        assert url("add_expense") in form.group(0), "Form action must be /expenses/add"

    def test_get_category_select_has_exactly_the_seven_options(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        assert select_option_labels(html) == CATEGORIES

    def test_get_form_has_all_four_fields(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        for name in ("amount", "date", "description"):
            input_tag(html, name)
        assert 'name="category"' in html

    def test_get_amount_input_constraints(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)
        tag = input_tag(html, "amount")

        assert 'type="number"' in tag
        assert 'step="0.01"' in tag
        assert 'min="0.01"' in tag
        assert "required" in tag

    def test_get_date_input_is_required_and_defaults_to_today(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)
        tag = input_tag(html, "date")

        assert 'type="date"' in tag
        assert "required" in tag
        assert date.today().isoformat() in tag, "Date should default to today"

    def test_get_description_input_is_optional_and_max_200(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)
        tag = input_tag(html, "description")

        assert 'maxlength="200"' in tag
        assert "required" not in tag, "Description is optional"

    def test_get_page_has_save_button_and_cancel_link_to_profile(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        assert "Save Expense" in html
        assert f'href="{url("profile")}"' in html, "Expected a cancel link to profile"

    def test_get_page_shows_no_error_initially(self, demo_client):
        response = demo_client.get(url("add_expense"))

        assert not has_error(response), "No error expected before submitting"

    def test_get_page_never_shows_pound_or_dollar_currency(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        assert "£" not in html
        assert "$" not in html


# ------------------------------------------------------------------ #
# POST /expenses/add: auth guard                                      #
# ------------------------------------------------------------------ #

class TestAddExpensePostAuth:
    def test_post_logged_out_redirects_to_login(self, client):
        response = client.post(url("add_expense"), data=VALID_FORM)

        assert response.status_code == 302
        assert path_of(response) == url("login")

    def test_post_logged_out_inserts_nothing(self, client):
        before = expense_count()

        client.post(url("add_expense"), data=VALID_FORM)

        assert expense_count() == before

    def test_post_after_logout_redirects_to_login(self, demo_client):
        demo_client.get(url("logout"))

        response = demo_client.post(url("add_expense"), data=VALID_FORM)

        assert response.status_code == 302
        assert path_of(response) == url("login")


# ------------------------------------------------------------------ #
# POST /expenses/add: success                                         #
# ------------------------------------------------------------------ #

class TestAddExpensePostSuccess:
    def test_post_valid_data_redirects_to_profile(self, empty_client):
        response = empty_client.post(url("add_expense"), data=VALID_FORM)

        assert response.status_code == 302
        assert path_of(response) == url("profile")

    def test_post_valid_data_stores_row_for_session_user(
        self, empty_client, empty_user_id
    ):
        empty_client.post(url("add_expense"), data=VALID_FORM)

        rows = expenses_for(empty_user_id)
        assert len(rows) == 1, "Expected one new expense for the session user"
        row = rows[0]
        assert row["user_id"] == empty_user_id
        assert row["amount"] == pytest.approx(50.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_post_valid_data_increases_total_by_exactly_one(self, demo_client):
        before = expense_count()

        demo_client.post(url("add_expense"), data=VALID_FORM)

        assert expense_count() == before + 1

    def test_post_valid_data_does_not_alter_other_users_expenses(
        self, empty_client, demo_user_id
    ):
        before = [tuple(r) for r in expenses_for(demo_user_id)]

        empty_client.post(url("add_expense"), data=VALID_FORM)

        assert [tuple(r) for r in expenses_for(demo_user_id)] == before

    def test_post_valid_data_appears_on_profile_transaction_list(self, empty_client):
        response = empty_client.post(
            url("add_expense"),
            data=form_with(description="Unique marker lunch", amount="77.5"),
            follow_redirects=True,
        )

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Unique marker lunch" in html, "New expense should be listed"
        assert "₹" in html, "Currency must display as rupees"

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_post_each_valid_category_is_accepted(
        self, empty_client, empty_user_id, category
    ):
        response = empty_client.post(
            url("add_expense"), data=form_with(category=category)
        )

        assert response.status_code == 302
        assert [r["category"] for r in expenses_for(empty_user_id)] == [category]

    @pytest.mark.parametrize(
        "raw, expected",
        [("0.01", 0.01), ("1", 1.0), ("99.99", 99.99), ("100000", 100000.0)],
    )
    def test_post_positive_amounts_are_stored_numerically(
        self, empty_client, empty_user_id, raw, expected
    ):
        response = empty_client.post(url("add_expense"), data=form_with(amount=raw))

        assert response.status_code == 302
        assert expenses_for(empty_user_id)[0]["amount"] == pytest.approx(expected)

    def test_post_forged_user_id_is_ignored(
        self, empty_client, empty_user_id, demo_user_id
    ):
        demo_before = len(expenses_for(demo_user_id))

        empty_client.post(
            url("add_expense"), data=form_with(user_id=str(demo_user_id))
        )

        assert len(expenses_for(demo_user_id)) == demo_before, (
            "Forged user_id must not attribute the expense to another user"
        )
        rows = expenses_for(empty_user_id)
        assert len(rows) == 1 and rows[0]["user_id"] == empty_user_id

    def test_post_two_submissions_create_two_rows(self, empty_client, empty_user_id):
        empty_client.post(url("add_expense"), data=form_with(description="one"))
        empty_client.post(url("add_expense"), data=form_with(description="two"))

        assert [r["description"] for r in expenses_for(empty_user_id)] == [
            "one",
            "two",
        ]


# ------------------------------------------------------------------ #
# POST /expenses/add: description handling                            #
# ------------------------------------------------------------------ #

class TestAddExpenseDescription:
    def test_post_missing_description_field_stores_null(
        self, empty_client, empty_user_id
    ):
        data = form_with()
        del data["description"]

        response = empty_client.post(url("add_expense"), data=data)

        assert response.status_code == 302
        assert path_of(response) == url("profile")
        rows = expenses_for(empty_user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None

    @pytest.mark.parametrize("blank", ["", " ", "     ", "\t"])
    def test_post_blank_description_stores_null(
        self, empty_client, empty_user_id, blank
    ):
        response = empty_client.post(
            url("add_expense"), data=form_with(description=blank)
        )

        assert response.status_code == 302
        assert expenses_for(empty_user_id)[0]["description"] is None

    def test_post_description_is_stripped(self, empty_client, empty_user_id):
        empty_client.post(
            url("add_expense"), data=form_with(description="   Lunch out   ")
        )

        assert expenses_for(empty_user_id)[0]["description"] == "Lunch out"

    def test_post_sql_injection_in_description_is_stored_literally(
        self, empty_client, empty_user_id
    ):
        evil = "x'); DROP TABLE expenses;--"

        response = empty_client.post(
            url("add_expense"), data=form_with(description=evil)
        )

        assert response.status_code == 302
        assert expenses_for(empty_user_id)[0]["description"] == evil
        assert expense_count() >= 1, "expenses table must still exist"

    def test_post_unicode_description_round_trips(self, empty_client, empty_user_id):
        text = "Chai ☕ and samosa ₹"

        empty_client.post(url("add_expense"), data=form_with(description=text))

        assert expenses_for(empty_user_id)[0]["description"] == text


# ------------------------------------------------------------------ #
# POST /expenses/add: validation errors                               #
# ------------------------------------------------------------------ #

INVALID_AMOUNTS = [
    pytest.param(None, id="missing"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace"),
    pytest.param("0", id="zero"),
    pytest.param("0.0", id="zero-decimal"),
    pytest.param("-5", id="negative"),
    pytest.param("-0.01", id="negative-decimal"),
    pytest.param("abc", id="non-numeric"),
    pytest.param("12abc", id="trailing-text"),
    pytest.param("1,5", id="comma-decimal"),
    pytest.param("nan", id="nan"),
    pytest.param("inf", id="infinity"),
]

INVALID_CATEGORIES = [
    pytest.param(None, id="missing"),
    pytest.param("", id="empty"),
    pytest.param("Groceries", id="not-in-list"),
    pytest.param("food", id="wrong-case"),
    pytest.param("'; DROP TABLE expenses;--", id="sql-injection"),
]

INVALID_DATES = [
    pytest.param(None, id="missing"),
    pytest.param("", id="empty"),
    pytest.param("not-a-date", id="text"),
    pytest.param("2026-13-01", id="month-13"),
    pytest.param("2026-02-30", id="feb-30"),
    pytest.param("2026-00-10", id="month-0"),
    pytest.param("20-03-2026", id="dd-mm-yyyy"),
    pytest.param("2026/03/20", id="slashes"),
]


def post_invalid(client, **overrides):
    """POST valid data with overrides; a value of None drops that field."""
    data = form_with(**overrides)
    data = {k: v for k, v in data.items() if v is not None}
    return client.post(url("add_expense"), data=data)


class TestAddExpenseValidation:
    @pytest.mark.parametrize("amount", INVALID_AMOUNTS)
    def test_post_invalid_amount_rerenders_form_with_error(
        self, empty_client, amount
    ):
        response = post_invalid(empty_client, amount=amount)

        assert response.status_code == 200, "Invalid amount must re-render the form"
        assert has_error(response), "Expected an error message"
        assert b"<form" in response.data

    @pytest.mark.parametrize("amount", INVALID_AMOUNTS)
    def test_post_invalid_amount_inserts_nothing(
        self, empty_client, empty_user_id, amount
    ):
        before = expense_count()

        post_invalid(empty_client, amount=amount)

        assert expense_count() == before
        assert expenses_for(empty_user_id) == []

    @pytest.mark.parametrize("category", INVALID_CATEGORIES)
    def test_post_invalid_category_rerenders_form_with_error(
        self, empty_client, category
    ):
        response = post_invalid(empty_client, category=category)

        assert response.status_code == 200
        assert has_error(response), "Expected an error message"
        assert b"<form" in response.data

    @pytest.mark.parametrize("category", INVALID_CATEGORIES)
    def test_post_invalid_category_inserts_nothing(
        self, empty_client, empty_user_id, category
    ):
        before = expense_count()

        post_invalid(empty_client, category=category)

        assert expense_count() == before
        assert expenses_for(empty_user_id) == []

    @pytest.mark.parametrize("date_value", INVALID_DATES)
    def test_post_invalid_date_rerenders_form_with_error(
        self, empty_client, date_value
    ):
        response = post_invalid(empty_client, date=date_value)

        assert response.status_code == 200
        assert has_error(response), "Expected an error message"
        assert b"<form" in response.data

    @pytest.mark.parametrize("date_value", INVALID_DATES)
    def test_post_invalid_date_inserts_nothing(
        self, empty_client, empty_user_id, date_value
    ):
        before = expense_count()

        post_invalid(empty_client, date=date_value)

        assert expense_count() == before
        assert expenses_for(empty_user_id) == []

    def test_post_empty_form_rerenders_with_error_and_inserts_nothing(
        self, empty_client, empty_user_id
    ):
        response = empty_client.post(url("add_expense"), data={})

        assert response.status_code == 200
        assert has_error(response)
        assert expenses_for(empty_user_id) == []

    def test_post_validation_error_does_not_redirect(self, empty_client):
        response = post_invalid(empty_client, amount="0")

        assert "Location" not in response.headers


class TestAddExpenseRepopulation:
    """After a validation error the submitted values must be kept."""

    def test_missing_amount_keeps_other_values(self, empty_client):
        response = post_invalid(
            empty_client,
            amount=None,
            category="Transport",
            date="2026-04-15",
            description="Keep this note",
        )
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Keep this note" in html, "Description should be retained"
        assert "2026-04-15" in html, "Date should be retained"
        assert re.search(
            r'<option[^>]*value="Transport"[^>]*selected', html
        ) or re.search(
            r'<option[^>]*selected[^>]*value="Transport"', html
        ), "Category should remain selected"

    def test_zero_amount_keeps_submitted_values(self, empty_client):
        response = post_invalid(
            empty_client,
            amount="0",
            category="Health",
            date="2026-05-01",
            description="Zero amount note",
        )
        html = response.get_data(as_text=True)

        assert "Zero amount note" in html
        assert "2026-05-01" in html
        assert re.search(r'<option[^>]*value="Health"[^>]*selected', html) or (
            re.search(r'<option[^>]*selected[^>]*value="Health"', html)
        )
        assert re.search(r'name="amount"[^>]*value="0"|value="0"[^>]*name="amount"', html), (
            "Submitted amount should be retained"
        )

    def test_non_numeric_amount_is_echoed_back(self, empty_client):
        response = post_invalid(empty_client, amount="abc", description="note abc")
        html = response.get_data(as_text=True)

        assert 'value="abc"' in html, "Submitted amount text should be retained"
        assert "note abc" in html

    def test_invalid_category_keeps_amount_date_description(self, empty_client):
        response = post_invalid(
            empty_client,
            amount="42.5",
            category="Groceries",
            date="2026-06-06",
            description="Bad category note",
        )
        html = response.get_data(as_text=True)

        assert "42.5" in html
        assert "2026-06-06" in html
        assert "Bad category note" in html

    def test_invalid_date_keeps_amount_category_description(self, empty_client):
        response = post_invalid(
            empty_client,
            amount="19.99",
            category="Shopping",
            date="2026-02-30",
            description="Bad date note",
        )
        html = response.get_data(as_text=True)

        assert "19.99" in html
        assert "Bad date note" in html
        assert re.search(r'<option[^>]*value="Shopping"[^>]*selected', html) or (
            re.search(r'<option[^>]*selected[^>]*value="Shopping"', html)
        )

    def test_rerendered_form_still_lists_all_categories(self, empty_client):
        response = post_invalid(empty_client, amount="0")

        assert select_option_labels(response.get_data(as_text=True)) == CATEGORIES

    def test_user_input_is_html_escaped_on_rerender(self, empty_client):
        payload = '<script>alert("x")</script>'

        response = post_invalid(empty_client, amount="0", description=payload)

        assert payload.encode() not in response.data, "Input must be escaped"


# ------------------------------------------------------------------ #
# Navigation: navbar and profile page links                           #
# ------------------------------------------------------------------ #

class TestAddExpenseNavigation:
    def test_navbar_shows_add_expense_link_when_logged_in(self, demo_client):
        html = demo_client.get(url("profile")).get_data(as_text=True)

        assert f'href="{url("add_expense")}"' in html
        assert "Add Expense" in html

    def test_navbar_link_present_on_other_logged_in_pages(self, demo_client):
        html = demo_client.get(url("add_expense")).get_data(as_text=True)

        assert f'href="{url("add_expense")}"' in html

    @pytest.mark.parametrize("endpoint", ["landing", "login", "register", "terms"])
    def test_navbar_hides_add_expense_link_when_logged_out(self, client, endpoint):
        response = client.get(url(endpoint))
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert url("add_expense") not in html, "Link must be hidden when logged out"
        assert "Add Expense" not in html

    def test_navbar_link_disappears_after_logout(self, demo_client):
        demo_client.get(url("logout"))

        html = demo_client.get(url("landing")).get_data(as_text=True)

        assert url("add_expense") not in html

    def test_profile_page_has_add_expense_button(self, empty_client):
        html = empty_client.get(url("profile")).get_data(as_text=True)

        # One occurrence is the navbar link; the page button is a second one.
        assert html.count(f'href="{url("add_expense")}"') >= 2, (
            "Expected both a navbar link and a profile-page button"
        )

    def test_profile_page_button_target_is_reachable(self, demo_client):
        response = demo_client.get(url("add_expense"))

        assert response.status_code == 200


# ------------------------------------------------------------------ #
# Edit / delete stubs remain untouched                                #
# ------------------------------------------------------------------ #

class TestStubsUntouched:
    def test_edit_stub_still_returns_step_8_placeholder(self, demo_client):
        response = demo_client.get(url("edit_expense", id=1))

        assert response.status_code == 200
        assert b"Step 8" in response.data

    def test_delete_stub_still_returns_step_9_placeholder(self, demo_client):
        response = demo_client.get(url("delete_expense", id=1))

        assert response.status_code == 200
        assert b"Step 9" in response.data

    def test_edit_and_delete_stubs_do_not_modify_expenses(self, demo_client):
        before = expense_count()

        demo_client.get(url("edit_expense", id=1))
        demo_client.get(url("delete_expense", id=1))

        assert expense_count() == before
