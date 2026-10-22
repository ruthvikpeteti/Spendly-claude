"""Tests for Step 8: Edit Expense.

Written from .claude/specs/08-edit-expense.md (CLAUDE.md wins on conflicts):
  * GET/POST /expenses/<id>/edit  (logged-in only, owner only)
  * update_expense (write helper)   -> database/db.py
  * get_expense_by_id (read helper) -> database/queries.py
  * get_recent_transactions exposes each row's id
  * profile.html: "Actions" column and an "Edit" link per transaction row
"""

from html.parser import HTMLParser
from urllib.parse import urlparse

import pytest
from flask import url_for

from app import app as flask_app
from database import db
from database.queries import get_expense_by_id, get_recent_transactions
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

ORIGINAL = {
    "amount": 42.5,
    "category": "Food",
    "date": "2026-01-15",
    "description": "Original lunch",
}


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


class PageParser(HTMLParser):
    """Collect the form-related elements of a page."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self.inputs = []
        self.selects = []
        self.options = []  # (select_name, attrs, text)
        self.textareas = {}
        self.anchors = []  # (attrs, text)
        self.headers = []  # <th> text
        self.buttons = []  # <button> text
        self._select = None
        self._option = None
        self._anchor = None
        self._th = None
        self._button = None
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.forms.append(attrs)
        elif tag == "input":
            self.inputs.append(attrs)
        elif tag == "select":
            self._select = attrs.get("name")
            self.selects.append(attrs)
        elif tag == "option":
            self._option = [self._select, attrs, ""]
        elif tag == "textarea":
            self._textarea = attrs.get("name")
            self.textareas[self._textarea] = ""
        elif tag == "a":
            self._anchor = [attrs, ""]
        elif tag == "th":
            self._th = ""
        elif tag == "button":
            self._button = ""

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        elif tag == "option" and self._option is not None:
            self.options.append(tuple(self._option))
            self._option = None
        elif tag == "textarea":
            self._textarea = None
        elif tag == "a" and self._anchor is not None:
            self.anchors.append((self._anchor[0], self._anchor[1].strip()))
            self._anchor = None
        elif tag == "th" and self._th is not None:
            self.headers.append(self._th.strip())
            self._th = None
        elif tag == "button" and self._button is not None:
            self.buttons.append(self._button.strip())
            self._button = None

    def handle_data(self, data):
        if self._option is not None:
            self._option[2] += data
        if self._anchor is not None:
            self._anchor[1] += data
        if self._th is not None:
            self._th += data
        if self._button is not None:
            self._button += data
        if self._textarea is not None:
            self.textareas[self._textarea] += data

    # convenience accessors -------------------------------------------------
    def input(self, name):
        for attrs in self.inputs:
            if attrs.get("name") == name:
                return attrs
        return None

    def field_value(self, name):
        """Value of an <input> (or <textarea>) named `name`; None if absent."""
        attrs = self.input(name)
        if attrs is not None:
            return attrs.get("value", "")
        if name in self.textareas:
            return self.textareas[name].strip("\r\n")
        return None

    def selected_categories(self):
        chosen = []
        for select_name, attrs, text in self.options:
            if select_name == "category" and "selected" in attrs:
                chosen.append(attrs.get("value", text.strip()))
        return chosen

    def category_values(self):
        return [
            attrs.get("value", text.strip())
            for select_name, attrs, text in self.options
            if select_name == "category"
        ]


def parse(response):
    parser = PageParser()
    parser.feed(response.get_data(as_text=True))
    return parser


def has_error(response):
    """True if the page shows an error element (class contains 'error' or role=alert)."""
    import re

    html = response.get_data(as_text=True)
    return (
        re.search(r'class="[^"]*error[^"]*"', html, re.IGNORECASE) is not None
        or 'role="alert"' in html
    )


def edit_url(expense_id):
    with flask_app.test_request_context():
        return url_for("edit_expense", id=expense_id)


def profile_url():
    with flask_app.test_request_context():
        return url_for("profile")


def login_url():
    with flask_app.test_request_context():
        return url_for("login")


def row_of(expense_id):
    """Raw DB row (all columns) for an expense, as a tuple, or None."""
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()
    return tuple(row) if row is not None else None


def all_rows():
    conn = db.get_db()
    try:
        return [
            tuple(r)
            for r in conn.execute("SELECT * FROM expenses ORDER BY id").fetchall()
        ]
    finally:
        conn.close()


def valid_form(**overrides):
    form = {
        "amount": "99.50",
        "category": "Transport",
        "date": "2026-02-20",
        "description": "Updated cab ride",
    }
    form.update(overrides)
    return form


def assert_redirects_to(response, path):
    assert (
        response.status_code == 302
    ), f"Expected 302 redirect, got {response.status_code}"
    assert (
        urlparse(response.headers["Location"]).path == path
    ), f"Expected redirect to {path}, got {response.headers['Location']}"


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def owner_id(empty_user_id):
    """User who owns the expense under test (starts with no other expenses)."""
    return empty_user_id


@pytest.fixture
def expense_id(owner_id):
    """An expense with known values owned by owner_id."""
    return db.create_expense(
        owner_id,
        ORIGINAL["amount"],
        ORIGINAL["category"],
        ORIGINAL["date"],
        ORIGINAL["description"],
    )


@pytest.fixture
def owner_client(client, owner_id):
    login(client, owner_id, "Empty User")
    return client


@pytest.fixture
def other_user_id(fresh_db):
    """A second registered user, different from owner_id."""
    return db.create_user("Other User", "other@example.com", "password123")


@pytest.fixture
def other_expense_id(other_user_id):
    return db.create_expense(other_user_id, 10.0, "Bills", "2026-01-01", "Theirs")


# ------------------------------------------------------------------ #
# Unit: get_expense_by_id                                             #
# ------------------------------------------------------------------ #


class TestGetExpenseById:
    def test_correct_owner_returns_matching_row(self, expense_id, owner_id):
        row = get_expense_by_id(expense_id, owner_id)
        assert row is not None, "Expected the owner's expense to be returned"
        assert row["id"] == expense_id
        assert float(row["amount"]) == ORIGINAL["amount"]
        assert row["category"] == ORIGINAL["category"]
        assert row["date"] == ORIGINAL["date"]
        assert row["description"] == ORIGINAL["description"]

    def test_wrong_user_returns_none(self, expense_id, other_user_id):
        assert (
            get_expense_by_id(expense_id, other_user_id) is None
        ), "Another user's expense must not be returned"

    def test_non_existent_expense_returns_none(self, owner_id):
        assert get_expense_by_id(999999, owner_id) is None

    def test_null_description_is_returned_as_none(self, owner_id):
        eid = db.create_expense(owner_id, 5.0, "Other", "2026-01-02", None)
        row = get_expense_by_id(eid, owner_id)
        assert row is not None
        assert row["description"] is None


# ------------------------------------------------------------------ #
# Unit: update_expense                                                #
# ------------------------------------------------------------------ #


class TestUpdateExpense:
    def test_owner_update_changes_row(self, expense_id, owner_id):
        db.update_expense(expense_id, owner_id, 99.0, "Bills", "2026-03-03", "New desc")
        row = get_expense_by_id(expense_id, owner_id)
        assert float(row["amount"]) == 99.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-03-03"
        assert row["description"] == "New desc"

    def test_update_with_none_description_stores_null(self, expense_id, owner_id):
        db.update_expense(expense_id, owner_id, 99.0, "Food", "2026-03-03", None)
        assert get_expense_by_id(expense_id, owner_id)["description"] is None

    def test_update_keeps_user_id(self, expense_id, owner_id):
        db.update_expense(expense_id, owner_id, 99.0, "Food", "2026-03-03", "x")
        conn = db.get_db()
        try:
            stored = conn.execute(
                "SELECT user_id FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert stored == owner_id

    def test_wrong_user_leaves_row_unchanged_without_error(
        self, expense_id, other_user_id
    ):
        before = row_of(expense_id)
        db.update_expense(
            expense_id, other_user_id, 99.0, "Bills", "2026-03-03", "Hijack"
        )
        assert (
            row_of(expense_id) == before
        ), "update_expense with a non-owner user_id must not modify the row"

    def test_update_does_not_touch_other_rows(self, expense_id, owner_id):
        sibling = db.create_expense(owner_id, 7.0, "Health", "2026-01-09", "Sibling")
        sibling_before = row_of(sibling)
        db.update_expense(expense_id, owner_id, 1.0, "Other", "2026-03-03", "x")
        assert row_of(sibling) == sibling_before

    def test_sql_injection_in_description_is_stored_literally(
        self, expense_id, owner_id
    ):
        payload = "x'); DROP TABLE expenses; --"
        db.update_expense(expense_id, owner_id, 1.0, "Other", "2026-03-03", payload)
        assert get_expense_by_id(expense_id, owner_id)["description"] == payload


# ------------------------------------------------------------------ #
# Unit: get_recent_transactions exposes id                            #
# ------------------------------------------------------------------ #


class TestRecentTransactionsExposeId:
    def test_each_transaction_has_id(self, demo_user_id):
        rows = get_recent_transactions(demo_user_id)
        assert rows, "Demo user should have transactions"
        for tx in rows:
            assert "id" in tx, "Each transaction must expose its expense id"

    def test_ids_match_database_rows(self, owner_id, expense_id):
        rows = get_recent_transactions(owner_id)
        assert [tx["id"] for tx in rows] == [expense_id]


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client, expense_id):
        response = client.get(edit_url(expense_id))
        assert_redirects_to(response, login_url())

    def test_post_logged_out_redirects_to_login(self, client, expense_id):
        response = client.post(edit_url(expense_id), data=valid_form())
        assert_redirects_to(response, login_url())

    def test_post_logged_out_does_not_modify_row(self, client, expense_id):
        before = row_of(expense_id)
        client.post(edit_url(expense_id), data=valid_form())
        assert row_of(expense_id) == before, "Logged-out POST must not change data"

    def test_logged_out_get_does_not_reveal_expense(self, client, expense_id):
        response = client.get(edit_url(expense_id))
        assert ORIGINAL["description"].encode() not in response.data


# ------------------------------------------------------------------ #
# Ownership / 404                                                     #
# ------------------------------------------------------------------ #


class TestOwnership:
    def test_get_other_users_expense_returns_404(self, owner_client, other_expense_id):
        response = owner_client.get(edit_url(other_expense_id))
        assert response.status_code == 404

    def test_get_non_existent_expense_returns_404(self, owner_client):
        response = owner_client.get(edit_url(999999))
        assert response.status_code == 404

    def test_post_other_users_expense_returns_404(self, owner_client, other_expense_id):
        response = owner_client.post(edit_url(other_expense_id), data=valid_form())
        assert response.status_code == 404

    def test_post_other_users_expense_modifies_nothing(
        self, owner_client, other_expense_id
    ):
        before = all_rows()
        owner_client.post(edit_url(other_expense_id), data=valid_form())
        assert all_rows() == before, "No rows may change on a non-owner POST"

    def test_post_other_users_expense_with_invalid_data_still_404(
        self, owner_client, other_expense_id
    ):
        response = owner_client.post(
            edit_url(other_expense_id), data=valid_form(amount="abc")
        )
        assert (
            response.status_code == 404
        ), "Ownership must be enforced before validation"

    def test_post_non_existent_expense_returns_404(self, owner_client):
        response = owner_client.post(edit_url(999999), data=valid_form())
        assert response.status_code == 404

    def test_post_non_existent_expense_creates_no_row(self, owner_client):
        before = all_rows()
        owner_client.post(edit_url(999999), data=valid_form())
        assert all_rows() == before

    def test_get_404_page_does_not_leak_other_users_data(
        self, owner_client, other_expense_id
    ):
        response = owner_client.get(edit_url(other_expense_id))
        assert b"Theirs" not in response.data

    def test_demo_user_cannot_edit_another_users_expense(
        self, client, demo_user_id, other_expense_id
    ):
        login(client, demo_user_id, "Demo User")
        assert client.get(edit_url(other_expense_id)).status_code == 404
        assert (
            client.post(edit_url(other_expense_id), data=valid_form()).status_code
            == 404
        )

    def test_user_cannot_edit_demo_users_expense(self, owner_client, demo_user_id):
        demo_expense = get_recent_transactions(demo_user_id)[0]["id"]
        before = row_of(demo_expense)
        assert owner_client.get(edit_url(demo_expense)).status_code == 404
        assert (
            owner_client.post(edit_url(demo_expense), data=valid_form()).status_code
            == 404
        )
        assert row_of(demo_expense) == before


# ------------------------------------------------------------------ #
# GET: form rendering                                                 #
# ------------------------------------------------------------------ #


class TestEditFormRendering:
    def test_get_own_expense_returns_200(self, owner_client, expense_id):
        response = owner_client.get(edit_url(expense_id))
        assert response.status_code == 200

    def test_page_extends_base_layout(self, owner_client, expense_id):
        response = owner_client.get(edit_url(expense_id))
        assert b"Spendly" in response.data, "Expected base.html branding"

    def test_form_posts_to_edit_url(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        posting = [f for f in page.forms if (f.get("method") or "").lower() == "post"]
        assert posting, "Expected a form with method=POST"
        assert any(
            urlparse(f.get("action", "")).path == edit_url(expense_id) for f in posting
        ), "Form action must point at this expense's edit URL"

    def test_amount_is_prefilled(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        value = page.field_value("amount")
        assert value not in (None, ""), "Amount input must be pre-filled"
        assert float(value) == ORIGINAL["amount"]

    def test_date_is_prefilled(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        assert page.field_value("date") == ORIGINAL["date"]

    def test_description_is_prefilled(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        assert page.field_value("description") == ORIGINAL["description"]

    def test_null_description_renders_empty_field(self, owner_client, owner_id):
        eid = db.create_expense(owner_id, 5.0, "Other", "2026-01-02", None)
        page = parse(owner_client.get(edit_url(eid)))
        assert page.field_value("description") in ("", None)
        assert "None" != page.field_value(
            "description"
        ), "A NULL description must not render as the text 'None'"

    def test_amount_input_attributes(self, owner_client, expense_id):
        attrs = parse(owner_client.get(edit_url(expense_id))).input("amount")
        assert attrs is not None, "Expected an input named 'amount'"
        assert attrs.get("type") == "number"
        assert attrs.get("step") == "0.01"
        assert attrs.get("min") == "0.01"
        assert "required" in attrs

    def test_date_input_attributes(self, owner_client, expense_id):
        attrs = parse(owner_client.get(edit_url(expense_id))).input("date")
        assert attrs is not None, "Expected an input named 'date'"
        assert attrs.get("type") == "date"
        assert "required" in attrs

    def test_description_is_optional_and_limited_to_200(self, owner_client, expense_id):
        attrs = parse(owner_client.get(edit_url(expense_id))).input("description")
        assert attrs is not None, "Expected an input named 'description'"
        assert "required" not in attrs
        assert attrs.get("maxlength") == "200"

    def test_category_select_has_exactly_the_seven_categories(
        self, owner_client, expense_id
    ):
        page = parse(owner_client.get(edit_url(expense_id)))
        assert [s.get("name") for s in page.selects] == ["category"]
        assert sorted(page.category_values()) == sorted(CATEGORIES)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_current_category_is_preselected(self, owner_client, owner_id, category):
        eid = db.create_expense(owner_id, 5.0, category, "2026-01-02", "x")
        page = parse(owner_client.get(edit_url(eid)))
        assert page.selected_categories() == [
            category
        ], f"Expected only {category} to be pre-selected"

    def test_has_save_changes_button(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        assert "Save Changes" in page.buttons or b"Save Changes" in (
            owner_client.get(edit_url(expense_id)).data
        )

    def test_has_cancel_link_to_profile(self, owner_client, expense_id):
        page = parse(owner_client.get(edit_url(expense_id)))
        hrefs = [attrs.get("href") for attrs, _ in page.anchors]
        assert profile_url() in hrefs, "Expected a cancel link back to /profile"

    def test_no_error_shown_on_initial_get(self, owner_client, expense_id):
        response = owner_client.get(edit_url(expense_id))
        assert not has_error(response), "No error expected before submitting"

    def test_html_in_description_is_escaped(self, owner_client, owner_id):
        payload = '<script>alert("x")</script>'
        eid = db.create_expense(owner_id, 5.0, "Other", "2026-01-02", payload)
        response = owner_client.get(edit_url(eid))
        assert payload.encode() not in response.data, "Description must be escaped"


# ------------------------------------------------------------------ #
# POST: success                                                       #
# ------------------------------------------------------------------ #


class TestEditSuccess:
    def test_valid_post_redirects_to_profile(self, owner_client, expense_id):
        response = owner_client.post(edit_url(expense_id), data=valid_form())
        assert_redirects_to(response, profile_url())

    def test_valid_post_updates_database(self, owner_client, expense_id):
        owner_client.post(edit_url(expense_id), data=valid_form())
        row = get_expense_by_id(
            expense_id, db.get_user_by_email("empty@example.com")["id"]
        )
        assert float(row["amount"]) == 99.5
        assert row["category"] == "Transport"
        assert row["date"] == "2026-02-20"
        assert row["description"] == "Updated cab ride"

    def test_integer_amount_is_accepted(self, owner_client, expense_id, owner_id):
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(amount="100")
        )
        assert_redirects_to(response, profile_url())
        assert float(get_expense_by_id(expense_id, owner_id)["amount"]) == 100.0

    def test_small_positive_amount_is_accepted(
        self, owner_client, expense_id, owner_id
    ):
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(amount="0.01")
        )
        assert_redirects_to(response, profile_url())
        assert float(get_expense_by_id(expense_id, owner_id)["amount"]) == 0.01

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_is_accepted(
        self, owner_client, expense_id, owner_id, category
    ):
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(category=category)
        )
        assert_redirects_to(response, profile_url())
        assert get_expense_by_id(expense_id, owner_id)["category"] == category

    def test_user_id_is_unchanged(self, owner_client, expense_id, owner_id):
        owner_client.post(edit_url(expense_id), data=valid_form())
        assert row_of(expense_id)[1] == owner_id, "user_id must not change"

    def test_id_and_created_at_are_unchanged(self, owner_client, expense_id):
        before = row_of(expense_id)
        owner_client.post(edit_url(expense_id), data=valid_form())
        after = row_of(expense_id)
        assert after[0] == before[0]
        assert after[-1] == before[-1], "created_at must not change"

    def test_other_rows_are_untouched(self, owner_client, expense_id, other_expense_id):
        sibling = db.create_expense(
            db.get_user_by_email("empty@example.com")["id"],
            3.0,
            "Health",
            "2026-01-05",
            "Sibling",
        )
        others_before = {r[0]: r for r in all_rows() if r[0] != expense_id}
        owner_client.post(edit_url(expense_id), data=valid_form())
        others_after = {r[0]: r for r in all_rows() if r[0] != expense_id}
        assert others_after == others_before
        assert sibling in others_after and other_expense_id in others_after

    def test_row_count_is_unchanged(self, owner_client, expense_id):
        before = len(all_rows())
        owner_client.post(edit_url(expense_id), data=valid_form())
        assert len(all_rows()) == before, "Edit must update, not insert"

    def test_demo_user_edit_leaves_their_other_expenses(self, client, demo_user_id):
        login(client, demo_user_id, "Demo User")
        target = get_recent_transactions(demo_user_id)[0]["id"]
        before = {r[0]: r for r in all_rows() if r[0] != target}
        response = client.post(edit_url(target), data=valid_form())
        assert_redirects_to(response, profile_url())
        after = {r[0]: r for r in all_rows() if r[0] != target}
        assert after == before

    def test_updated_values_appear_on_profile(self, owner_client, expense_id):
        response = owner_client.post(
            edit_url(expense_id),
            data=valid_form(description="Unique-edited-desc-123"),
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Unique-edited-desc-123" in response.data
        assert b"Original lunch" not in response.data
        assert "₹99.50".encode() in response.data, "Expected updated amount in rupees"

    def test_description_is_stripped(self, owner_client, expense_id, owner_id):
        owner_client.post(
            edit_url(expense_id), data=valid_form(description="   padded   ")
        )
        assert get_expense_by_id(expense_id, owner_id)["description"] == "padded"

    def test_description_of_exactly_200_chars_is_accepted(
        self, owner_client, expense_id, owner_id
    ):
        text = "a" * 200
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(description=text)
        )
        assert_redirects_to(response, profile_url())
        assert get_expense_by_id(expense_id, owner_id)["description"] == text

    def test_sql_injection_description_stored_literally(
        self, owner_client, expense_id, owner_id
    ):
        payload = "'; DROP TABLE expenses; --"
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(description=payload)
        )
        assert_redirects_to(response, profile_url())
        assert get_expense_by_id(expense_id, owner_id)["description"] == payload
        assert row_of(expense_id) is not None, "expenses table must still exist"

    def test_unchanged_resubmission_succeeds(self, owner_client, expense_id, owner_id):
        response = owner_client.post(
            edit_url(expense_id),
            data={
                "amount": str(ORIGINAL["amount"]),
                "category": ORIGINAL["category"],
                "date": ORIGINAL["date"],
                "description": ORIGINAL["description"],
            },
        )
        assert_redirects_to(response, profile_url())
        row = get_expense_by_id(expense_id, owner_id)
        assert float(row["amount"]) == ORIGINAL["amount"]
        assert row["description"] == ORIGINAL["description"]


# ------------------------------------------------------------------ #
# POST: blank description -> NULL                                     #
# ------------------------------------------------------------------ #


class TestBlankDescription:
    @pytest.mark.parametrize("blank", ["", "   ", "\t "])
    def test_blank_description_stored_as_null(self, owner_client, expense_id, blank):
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(description=blank)
        )
        assert_redirects_to(response, profile_url())
        conn = db.get_db()
        try:
            stored = conn.execute(
                "SELECT description FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert stored is None, f"Expected NULL description, got {stored!r}"

    def test_missing_description_field_stored_as_null(
        self, owner_client, expense_id, owner_id
    ):
        form = valid_form()
        del form["description"]
        response = owner_client.post(edit_url(expense_id), data=form)
        assert_redirects_to(response, profile_url())
        assert get_expense_by_id(expense_id, owner_id)["description"] is None

    def test_other_fields_still_saved_when_description_blank(
        self, owner_client, expense_id, owner_id
    ):
        owner_client.post(edit_url(expense_id), data=valid_form(description=""))
        row = get_expense_by_id(expense_id, owner_id)
        assert float(row["amount"]) == 99.5
        assert row["category"] == "Transport"
        assert row["date"] == "2026-02-20"


# ------------------------------------------------------------------ #
# POST: validation errors                                             #
# ------------------------------------------------------------------ #

INVALID_SUBMISSIONS = [
    pytest.param(valid_form(amount=""), id="amount-empty"),
    pytest.param(valid_form(amount="   "), id="amount-whitespace"),
    pytest.param(valid_form(amount="0"), id="amount-zero"),
    pytest.param(valid_form(amount="0.00"), id="amount-zero-decimal"),
    pytest.param(valid_form(amount="-5"), id="amount-negative"),
    pytest.param(valid_form(amount="-0.01"), id="amount-negative-decimal"),
    pytest.param(valid_form(amount="abc"), id="amount-non-numeric"),
    pytest.param(valid_form(amount="12abc"), id="amount-partly-numeric"),
    pytest.param(valid_form(category=""), id="category-empty"),
    pytest.param(valid_form(category="Groceries"), id="category-unknown"),
    pytest.param(valid_form(category="food"), id="category-wrong-case"),
    pytest.param(
        valid_form(category="Food'; DROP TABLE expenses;--"), id="category-sqli"
    ),
    pytest.param(valid_form(date=""), id="date-empty"),
    pytest.param(valid_form(date="not-a-date"), id="date-garbage"),
    pytest.param(valid_form(date="2026-13-01"), id="date-bad-month"),
    pytest.param(valid_form(date="2026-02-30"), id="date-impossible-day"),
    pytest.param(valid_form(date="20/02/2026"), id="date-wrong-format"),
    pytest.param(valid_form(description="d" * 201), id="description-201-chars"),
    pytest.param(valid_form(description="d" * 1000), id="description-1000-chars"),
]


class TestValidationErrors:
    @pytest.mark.parametrize("form", INVALID_SUBMISSIONS)
    def test_invalid_input_rerenders_form_with_200(
        self, owner_client, expense_id, form
    ):
        response = owner_client.post(edit_url(expense_id), data=form)
        assert (
            response.status_code == 200
        ), f"Expected form re-render (200), got {response.status_code}"
        assert parse(response).input("amount") is not None, "Expected the form again"

    @pytest.mark.parametrize("form", INVALID_SUBMISSIONS)
    def test_invalid_input_shows_error_message(self, owner_client, expense_id, form):
        response = owner_client.post(edit_url(expense_id), data=form)
        assert has_error(response), "Expected an error message on the page"

    @pytest.mark.parametrize("form", INVALID_SUBMISSIONS)
    def test_invalid_input_leaves_database_row_unchanged(
        self, owner_client, expense_id, form
    ):
        before = all_rows()
        owner_client.post(edit_url(expense_id), data=form)
        assert all_rows() == before, "Invalid submission must not change the DB"

    @pytest.mark.parametrize("form", INVALID_SUBMISSIONS)
    def test_invalid_input_does_not_redirect(self, owner_client, expense_id, form):
        response = owner_client.post(edit_url(expense_id), data=form)
        assert "Location" not in response.headers

    def test_missing_fields_entirely_rerenders_with_error(
        self, owner_client, expense_id
    ):
        before = all_rows()
        response = owner_client.post(edit_url(expense_id), data={})
        assert response.status_code == 200
        assert has_error(response)
        assert all_rows() == before

    def test_description_over_200_chars_is_not_truncated_and_saved(
        self, owner_client, expense_id, owner_id
    ):
        owner_client.post(edit_url(expense_id), data=valid_form(description="z" * 250))
        assert (
            get_expense_by_id(expense_id, owner_id)["description"]
            == ORIGINAL["description"]
        )


class TestSubmittedValuesRetained:
    """On error the form shows what the user submitted, not the DB values."""

    def test_invalid_category_retains_other_submitted_values(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(
                edit_url(expense_id),
                data=valid_form(
                    amount="77.5",
                    category="Bogus",
                    date="2026-03-04",
                    description="my submitted desc",
                ),
            )
        )
        assert float(page.field_value("amount")) == 77.5
        assert page.field_value("date") == "2026-03-04"
        assert page.field_value("description") == "my submitted desc"

    def test_invalid_date_retains_other_submitted_values(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(
                edit_url(expense_id),
                data=valid_form(
                    amount="55",
                    category="Health",
                    date="garbage",
                    description="keep me",
                ),
            )
        )
        assert float(page.field_value("amount")) == 55.0
        assert page.selected_categories() == ["Health"]
        assert page.field_value("description") == "keep me"

    def test_invalid_amount_retains_other_submitted_values(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(
                edit_url(expense_id),
                data=valid_form(
                    amount="0",
                    category="Shopping",
                    date="2026-05-06",
                    description="zero amount desc",
                ),
            )
        )
        assert page.selected_categories() == ["Shopping"]
        assert page.field_value("date") == "2026-05-06"
        assert page.field_value("description") == "zero amount desc"

    def test_zero_amount_is_retained_in_amount_field(self, owner_client, expense_id):
        page = parse(
            owner_client.post(edit_url(expense_id), data=valid_form(amount="0"))
        )
        assert (
            float(page.field_value("amount")) == 0.0
        ), "Submitted amount (0) should be shown again, not the DB amount"

    def test_negative_amount_is_retained_in_amount_field(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(edit_url(expense_id), data=valid_form(amount="-5"))
        )
        assert float(page.field_value("amount")) == -5.0

    def test_over_long_description_is_retained(self, owner_client, expense_id):
        long_text = "q" * 201
        page = parse(
            owner_client.post(
                edit_url(expense_id), data=valid_form(description=long_text)
            )
        )
        assert page.field_value("description") == long_text

    def test_original_db_values_are_not_shown_after_error(
        self, owner_client, expense_id
    ):
        response = owner_client.post(
            edit_url(expense_id),
            data=valid_form(category="Bogus", description="Different text"),
        )
        page = parse(response)
        assert page.field_value("description") != ORIGINAL["description"]
        assert page.field_value("date") != ORIGINAL["date"]
        assert float(page.field_value("amount")) != ORIGINAL["amount"]

    def test_submitted_category_is_preselected_after_other_field_error(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(
                edit_url(expense_id),
                data=valid_form(category="Entertainment", amount="abc"),
            )
        )
        assert page.selected_categories() == ["Entertainment"]

    def test_html_in_submitted_description_is_escaped_on_error(
        self, owner_client, expense_id
    ):
        payload = '<script>alert("x")</script>'
        response = owner_client.post(
            edit_url(expense_id), data=valid_form(amount="abc", description=payload)
        )
        assert (
            payload.encode() not in response.data
        ), "Submitted description must be HTML-escaped when re-rendered"

    def test_form_still_targets_same_expense_after_error(
        self, owner_client, expense_id
    ):
        page = parse(
            owner_client.post(edit_url(expense_id), data=valid_form(amount="abc"))
        )
        assert any(
            urlparse(f.get("action", "")).path == edit_url(expense_id)
            for f in page.forms
        ), "Re-rendered form must still post to this expense's edit URL"

    def test_can_fix_error_and_resubmit(self, owner_client, expense_id, owner_id):
        owner_client.post(edit_url(expense_id), data=valid_form(amount="abc"))
        response = owner_client.post(edit_url(expense_id), data=valid_form())
        assert_redirects_to(response, profile_url())
        assert float(get_expense_by_id(expense_id, owner_id)["amount"]) == 99.5


# ------------------------------------------------------------------ #
# Profile page: Actions column and Edit links                         #
# ------------------------------------------------------------------ #


class TestProfileEditLinks:
    def test_profile_has_actions_column_header(self, client, demo_user_id):
        login(client, demo_user_id, "Demo User")
        page = parse(client.get(profile_url()))
        assert (
            "Actions" in page.headers
        ), f"Expected an 'Actions' column header, got {page.headers}"

    def test_every_transaction_row_has_an_edit_link(self, client, demo_user_id):
        login(client, demo_user_id, "Demo User")
        page = parse(client.get(profile_url()))
        edit_hrefs = [
            attrs.get("href") for attrs, text in page.anchors if text == "Edit"
        ]
        expected = [edit_url(tx["id"]) for tx in get_recent_transactions(demo_user_id)]
        assert expected, "Demo user should have transactions"
        assert sorted(edit_hrefs) == sorted(
            expected
        ), "Each transaction needs an Edit link to its own edit URL"

    def test_edit_links_are_unique_per_row(self, client, demo_user_id):
        login(client, demo_user_id, "Demo User")
        page = parse(client.get(profile_url()))
        edit_hrefs = [
            attrs.get("href") for attrs, text in page.anchors if text == "Edit"
        ]
        assert len(edit_hrefs) == len(set(edit_hrefs))

    def test_edit_link_href_matches_expense_id(self, client, owner_client_pair):
        client, expense_id = owner_client_pair
        page = parse(client.get(profile_url()))
        edit_hrefs = [
            attrs.get("href") for attrs, text in page.anchors if text == "Edit"
        ]
        assert edit_hrefs == [f"/expenses/{expense_id}/edit"]

    def test_edit_link_leads_to_working_form(self, client, owner_client_pair):
        client, expense_id = owner_client_pair
        page = parse(client.get(profile_url()))
        href = next(a.get("href") for a, t in page.anchors if t == "Edit")
        response = client.get(href)
        assert response.status_code == 200
        assert parse(response).field_value("description") == ORIGINAL["description"]

    def test_profile_does_not_link_to_other_users_expenses(
        self, client, owner_client_pair, other_expense_id
    ):
        client, _ = owner_client_pair
        page = parse(client.get(profile_url()))
        hrefs = [a.get("href") for a, _ in page.anchors]
        assert edit_url(other_expense_id) not in hrefs

    def test_user_without_expenses_has_no_edit_links(self, client, empty_user_id):
        login(client, empty_user_id, "Empty User")
        response = client.get(profile_url())
        assert response.status_code == 200
        page = parse(response)
        assert not [t for _, t in page.anchors if t == "Edit"]

    def test_edit_links_respect_date_filter(self, client, owner_id):
        old = db.create_expense(owner_id, 1.0, "Food", "2020-01-01", "ancient")
        new = db.create_expense(owner_id, 2.0, "Food", "2026-01-01", "recent")
        login(client, owner_id, "Empty User")
        page = parse(client.get(profile_url(), query_string={"start": "2025-01-01"}))
        hrefs = [a.get("href") for a, t in page.anchors if t == "Edit"]
        assert hrefs == [edit_url(new)]
        assert edit_url(old) not in hrefs


@pytest.fixture
def owner_client_pair(client, owner_id, expense_id):
    """(logged-in client, expense_id) for a user with exactly one expense."""
    login(client, owner_id, "Empty User")
    return client, expense_id


# ------------------------------------------------------------------ #
# Scope guard: delete route is still the Step 9 placeholder           #
# ------------------------------------------------------------------ #


class TestDeleteRouteUntouched:
    def test_delete_route_is_still_step_9_placeholder(self, client, expense_id):
        with flask_app.test_request_context():
            url = url_for("delete_expense", id=expense_id)
        response = client.get(url)
        assert response.status_code == 200
        assert b"Step 9" in response.data

    def test_delete_route_does_not_delete_the_expense(self, client, expense_id):
        with flask_app.test_request_context():
            url = url_for("delete_expense", id=expense_id)
        client.get(url)
        assert row_of(expense_id) is not None
