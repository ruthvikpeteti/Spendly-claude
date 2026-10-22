"""Tests for Step 6: Date filter on the profile page.

Written from .claude/specs/06-date-filter-profile-page.md.

Seed data is dated relative to the current month, so tests that need exact
numbers insert their own expenses (fixed dates, or dates computed from today
for the quick-select tabs) for a freshly registered user.
"""
import calendar
import html as html_lib
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from flask import url_for

from app import app as flask_app
from app import date_presets
from conftest import login
from database import db, queries

TAB_LABELS = ["All time", "This month", "Last 3 months", "Custom"]


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def route_url(endpoint, **values):
    with flask_app.test_request_context():
        return url_for(endpoint, **values)


def add_expense(user_id, amount, category, day, description):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day, description),
        )
        conn.commit()
    finally:
        conn.close()


def month_start_back(today, months_back):
    """First day of the month `months_back` months before today's month."""
    index = today.year * 12 + (today.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def month_end(today):
    return today.replace(day=calendar.monthrange(today.year, today.month)[1])


def to_text(markup):
    markup = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S)
    markup = re.sub(r"<[^>]+>", " ", markup)
    return re.sub(r"\s+", " ", html_lib.unescape(markup)).strip()


def get_page(client, query=""):
    path = route_url("profile") + (f"?{query}" if query else "")
    response = client.get(path)
    assert response.status_code == 200, f"GET {path} returned {response.status_code}"
    return response.get_data(as_text=True)


def tabs(markup):
    """Return the four filter tabs as [{label, href, selected}] in page order."""
    found = []
    for attrs, inner in re.findall(r"<a\b([^>]*)>(.*?)</a>", markup, flags=re.S):
        label = to_text(inner)
        if label not in TAB_LABELS or any(t["label"] == label for t in found):
            continue
        href = re.search(r'href="([^"]*)"', attrs)
        found.append(
            {
                "label": label,
                "href": html_lib.unescape(href.group(1)) if href else "",
                "selected": 'aria-current="true"' in attrs,
            }
        )
    return found


def selected_tabs(markup):
    return [t["label"] for t in tabs(markup) if t["selected"]]


def tab_href(markup, label):
    return next(t["href"] for t in tabs(markup) if t["label"] == label)


def inputs(markup):
    result = []
    for attrs in re.findall(r"<input\b([^>]*)>", markup):
        result.append(
            {k: html_lib.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', attrs)}
        )
    return result


def date_inputs(markup):
    return [i for i in inputs(markup) if i.get("type") == "date"]


def stats(markup):
    text = to_text(markup)
    total = re.search(r"Total spent\s+(\S+)", text)
    count = re.search(r"\bTransactions\s+(\d+)", text)
    top = re.search(r"Top category\s+(\S+)", text)
    assert total and count and top, f"Stat tiles not found in page text: {text[:300]}"
    return {
        "total": total.group(1),
        "count": int(count.group(1)),
        "top": top.group(1),
    }


def transactions_text(markup):
    text = to_text(markup)
    assert "Recent transactions" in text and "Spending by category" in text
    return text.split("Recent transactions", 1)[1].split("Spending by category", 1)[0]


def breakdown_text(markup):
    markup = re.sub(r"<progress\b.*?</progress>", " ", markup, flags=re.S)
    return to_text(markup).split("Spending by category", 1)[1]


def words(markup):
    return set(to_text(markup).split())


def range_label(start, end):
    return re.compile(
        rf"Showing\s+{start.strftime('%d %b')}\s*[–-]\s*{end.strftime('%d %b')}"
    )


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def other_user_id(fresh_db):
    """A second user whose expenses must never leak into anyone else's view."""
    uid = db.create_user("Other Person", "other@example.com", "password123")
    add_expense(uid, 999.0, "Shopping", "2020-02-10", "OtherSecret")
    add_expense(uid, 888.0, "Shopping", date.today().isoformat(), "OtherToday")
    return uid


@pytest.fixture
def dated_user_id(empty_user_id):
    """Empty user plus expenses on fixed dates around a month boundary."""
    uid = empty_user_id
    add_expense(uid, 10.0, "Food", "2020-01-31", "jan-end")
    add_expense(uid, 20.0, "Food", "2020-02-01", "feb-start")
    add_expense(uid, 100.0, "Bills", "2020-02-15", "feb-mid")
    add_expense(uid, 40.0, "Health", "2020-02-29", "feb-last")
    add_expense(uid, 5.0, "Food", "2020-03-01", "mar-first")
    return uid


@pytest.fixture
def relative_user_id(empty_user_id):
    """Empty user plus expenses sitting on the quick-select range boundaries."""
    today = date.today()
    uid = empty_user_id
    this_first = today.replace(day=1)
    two_back_first = month_start_back(today, 2)
    add_expense(uid, 10.0, "Food", this_first.isoformat(), "cur-first")
    add_expense(uid, 20.0, "Bills", month_end(today).isoformat(), "cur-last")
    add_expense(uid, 30.0, "Health", (this_first - timedelta(days=1)).isoformat(), "prev-last")
    add_expense(uid, 40.0, "Transport", two_back_first.isoformat(), "two-first")
    add_expense(uid, 50.0, "Shopping", (two_back_first - timedelta(days=1)).isoformat(), "three-last")
    return uid


@pytest.fixture
def dated_client(client, dated_user_id, other_user_id):
    login(client, dated_user_id, "Empty User")
    return client


@pytest.fixture
def relative_client(client, relative_user_id, other_user_id):
    login(client, relative_user_id, "Empty User")
    return client


@pytest.fixture
def empty_client(client, empty_user_id):
    login(client, empty_user_id, "Empty User")
    return client


@pytest.fixture
def demo_client(client, demo_user_id):
    login(client, demo_user_id, "Demo User")
    return client


# ------------------------------------------------------------------ #
# Quick-select range computation                                      #
# ------------------------------------------------------------------ #

class TestDatePresets:
    def test_presets_example_october_2026(self):
        presets = date_presets(date(2026, 10, 22))
        by_label = {p["label"]: p for p in presets}
        assert by_label["This month"]["start"] == "2026-10-01"
        assert by_label["This month"]["end"] == "2026-10-31"
        assert by_label["Last 3 months"]["start"] == "2026-08-01"
        assert by_label["Last 3 months"]["end"] == "2026-10-31"

    def test_presets_are_ordered_all_time_first_without_bounds(self):
        presets = date_presets(date(2026, 10, 22))
        assert [p["label"] for p in presets] == TAB_LABELS[:3]
        assert presets[0]["start"] is None and presets[0]["end"] is None

    def test_last_3_months_rolls_back_over_year_boundary_in_january(self):
        by_label = {p["label"]: p for p in date_presets(date(2026, 1, 15))}
        assert by_label["Last 3 months"]["start"] == "2025-11-01"
        assert by_label["Last 3 months"]["end"] == "2026-01-31"
        assert by_label["This month"]["start"] == "2026-01-01"

    def test_february_leap_year_this_month_ends_on_29th(self):
        by_label = {p["label"]: p for p in date_presets(date(2028, 2, 10))}
        assert by_label["This month"]["end"] == "2028-02-29"
        assert by_label["Last 3 months"]["end"] == "2028-02-29"
        assert by_label["Last 3 months"]["start"] == "2027-12-01"

    @pytest.mark.parametrize(
        "today, month_start, month_end_, three_start",
        [
            (date(2027, 2, 28), "2027-02-01", "2027-02-28", "2026-12-01"),
            (date(2026, 2, 1), "2026-02-01", "2026-02-28", "2025-12-01"),
            (date(2026, 3, 31), "2026-03-01", "2026-03-31", "2026-01-01"),
            (date(2026, 12, 31), "2026-12-01", "2026-12-31", "2026-10-01"),
            (date(2026, 4, 30), "2026-04-01", "2026-04-30", "2026-02-01"),
        ],
    )
    def test_presets_for_various_dates(self, today, month_start, month_end_, three_start):
        by_label = {p["label"]: p for p in date_presets(today)}
        assert by_label["This month"]["start"] == month_start
        assert by_label["This month"]["end"] == month_end_
        assert by_label["Last 3 months"]["start"] == three_start
        assert by_label["Last 3 months"]["end"] == month_end_


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

class TestQueryHelpers:
    # --- get_summary_stats ------------------------------------------------
    def test_stats_without_bounds_include_everything_of_that_user(self, dated_user_id, other_user_id):
        result = queries.get_summary_stats(dated_user_id)
        assert result["total_spent"] == pytest.approx(175.0)
        assert result["transaction_count"] == 5
        assert result["top_category"] == "Bills"

    def test_stats_none_bounds_equal_omitted_bounds(self, dated_user_id):
        assert queries.get_summary_stats(dated_user_id, None, None) == queries.get_summary_stats(dated_user_id)

    def test_stats_with_both_bounds(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, "2020-02-01", "2020-02-29")
        assert result["total_spent"] == pytest.approx(160.0)
        assert result["transaction_count"] == 3
        assert result["top_category"] == "Bills"

    def test_stats_with_start_only(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, start_date="2020-02-15")
        assert result["transaction_count"] == 3
        assert result["total_spent"] == pytest.approx(145.0)

    def test_stats_with_end_only(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, end_date="2020-02-01")
        assert result["transaction_count"] == 2
        assert result["total_spent"] == pytest.approx(30.0)
        assert result["top_category"] == "Food"

    def test_stats_bounds_are_inclusive_on_both_ends(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, "2020-01-31", "2020-03-01")
        assert result["transaction_count"] == 5, "expenses on start and end dates must be included"

    def test_stats_single_day_range_returns_only_that_day(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, "2020-02-15", "2020-02-15")
        assert result["transaction_count"] == 1
        assert result["total_spent"] == pytest.approx(100.0)

    def test_stats_empty_range_returns_zero_and_dash(self, dated_user_id):
        result = queries.get_summary_stats(dated_user_id, "2021-01-01", "2021-12-31")
        assert result["total_spent"] == 0
        assert result["transaction_count"] == 0
        assert result["top_category"] == "—"

    def test_stats_never_include_another_users_expenses(self, dated_user_id, other_user_id):
        result = queries.get_summary_stats(dated_user_id, "2020-02-01", "2020-02-29")
        assert result["total_spent"] == pytest.approx(160.0), "other user's 999.00 leaked in"
        other = queries.get_summary_stats(other_user_id, "2020-02-01", "2020-02-29")
        assert other["total_spent"] == pytest.approx(999.0)
        assert other["top_category"] == "Shopping"

    # --- get_recent_transactions -----------------------------------------
    def test_transactions_without_bounds_newest_first(self, dated_user_id):
        rows = queries.get_recent_transactions(dated_user_id)
        assert [r["description"] for r in rows] == [
            "mar-first", "feb-last", "feb-mid", "feb-start", "jan-end",
        ]

    def test_transactions_with_bounds_only_within_range_newest_first(self, dated_user_id):
        rows = queries.get_recent_transactions(
            dated_user_id, start_date="2020-02-01", end_date="2020-02-29"
        )
        assert [r["description"] for r in rows] == ["feb-last", "feb-mid", "feb-start"]

    def test_transactions_inclusive_boundaries(self, dated_user_id):
        rows = queries.get_recent_transactions(
            dated_user_id, start_date="2020-02-01", end_date="2020-02-29"
        )
        dates = {r["date"] for r in rows}
        assert "2020-02-01" in dates and "2020-02-29" in dates

    def test_transactions_start_only_and_end_only(self, dated_user_id):
        after = queries.get_recent_transactions(dated_user_id, start_date="2020-02-29")
        before = queries.get_recent_transactions(dated_user_id, end_date="2020-01-31")
        assert [r["description"] for r in after] == ["mar-first", "feb-last"]
        assert [r["description"] for r in before] == ["jan-end"]

    def test_transactions_empty_range_returns_empty_list(self, dated_user_id):
        assert queries.get_recent_transactions(
            dated_user_id, start_date="2021-01-01", end_date="2021-01-31"
        ) == []

    def test_transactions_limit_applies_within_range(self, dated_user_id):
        rows = queries.get_recent_transactions(
            dated_user_id, limit=2, start_date="2020-02-01", end_date="2020-02-29"
        )
        assert [r["description"] for r in rows] == ["feb-last", "feb-mid"]

    def test_transactions_default_limit_is_ten_even_when_filtered(self, empty_user_id):
        for day in range(1, 13):
            add_expense(empty_user_id, 1.0, "Food", f"2020-05-{day:02d}", f"e{day}")
        rows = queries.get_recent_transactions(
            empty_user_id, start_date="2020-05-01", end_date="2020-05-31"
        )
        assert len(rows) == 10
        assert rows[0]["date"] == "2020-05-12"

    def test_transactions_never_include_another_users_expenses(self, dated_user_id, other_user_id):
        rows = queries.get_recent_transactions(
            dated_user_id, start_date="2020-02-01", end_date="2020-02-29"
        )
        assert all(r["description"] != "OtherSecret" for r in rows)
        assert all(r["amount"] != 999.0 for r in rows)

    def test_transactions_none_bounds_equal_omitted_bounds(self, dated_user_id):
        assert queries.get_recent_transactions(
            dated_user_id, start_date=None, end_date=None
        ) == queries.get_recent_transactions(dated_user_id)

    # --- get_category_breakdown ------------------------------------------
    def test_breakdown_without_bounds_covers_all_categories(self, dated_user_id):
        rows = queries.get_category_breakdown(dated_user_id)
        amounts = {r["name"]: r["amount"] for r in rows}
        assert amounts == {
            "Bills": pytest.approx(100.0),
            "Food": pytest.approx(35.0),
            "Health": pytest.approx(40.0),
        }

    def test_breakdown_with_bounds_only_counts_range(self, dated_user_id):
        rows = queries.get_category_breakdown(dated_user_id, "2020-02-01", "2020-02-29")
        amounts = {r["name"]: r["amount"] for r in rows}
        assert amounts == {
            "Bills": pytest.approx(100.0),
            "Health": pytest.approx(40.0),
            "Food": pytest.approx(20.0),
        }
        assert rows[0]["name"] == "Bills", "largest category first"

    def test_breakdown_inclusive_boundaries(self, dated_user_id):
        rows = queries.get_category_breakdown(dated_user_id, "2020-03-01", "2020-03-01")
        assert [(r["name"], r["amount"]) for r in rows] == [("Food", pytest.approx(5.0))]

    def test_breakdown_empty_range_returns_empty_list(self, dated_user_id):
        assert queries.get_category_breakdown(dated_user_id, "2021-01-01", "2021-12-31") == []

    @pytest.mark.parametrize(
        "start, end",
        [
            (None, None),
            ("2020-02-01", "2020-02-29"),
            ("2020-02-15", None),
            (None, "2020-02-15"),
            ("2020-01-31", "2020-03-01"),
        ],
    )
    def test_breakdown_percentages_sum_to_100(self, dated_user_id, start, end):
        rows = queries.get_category_breakdown(dated_user_id, start, end)
        assert rows, "expected some categories for this range"
        assert sum(r["pct"] for r in rows) == 100

    def test_breakdown_percentages_sum_to_100_with_awkward_thirds(self, empty_user_id):
        for cat in ("Food", "Bills", "Health"):
            add_expense(empty_user_id, 10.0, cat, "2020-06-10", cat)
        rows = queries.get_category_breakdown(empty_user_id, "2020-06-01", "2020-06-30")
        assert sum(r["pct"] for r in rows) == 100

    def test_breakdown_never_includes_another_users_expenses(self, dated_user_id, other_user_id):
        rows = queries.get_category_breakdown(dated_user_id, "2020-02-01", "2020-02-29")
        assert "Shopping" not in {r["name"] for r in rows}

    def test_breakdown_none_bounds_equal_omitted_bounds(self, dated_user_id):
        assert queries.get_category_breakdown(
            dated_user_id, None, None
        ) == queries.get_category_breakdown(dated_user_id)

    # --- unchanged behaviour on the seed account -------------------------
    def test_seed_account_all_time_unchanged(self, demo_user_id):
        result = queries.get_summary_stats(demo_user_id)
        assert result["total_spent"] == pytest.approx(401.50)
        assert result["transaction_count"] == 8
        assert result["top_category"] == "Bills"

    def test_sql_injection_in_helper_bounds_does_not_leak_or_crash(self, dated_user_id, other_user_id):
        payload = "2020-01-01' OR '1'='1"
        result = queries.get_summary_stats(dated_user_id, payload, None)
        assert result["total_spent"] != pytest.approx(175.0 + 999.0 + 888.0)
        rows = queries.get_recent_transactions(dated_user_id, start_date=payload)
        assert all(r["description"] not in ("OtherSecret", "OtherToday") for r in rows)


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    @pytest.mark.parametrize(
        "query",
        ["", "start=2026-10-01", "start=2026-10-01&end=2026-10-31", "range=custom", "start=bad"],
    )
    def test_logged_out_profile_redirects_to_login(self, client, query):
        path = route_url("profile") + (f"?{query}" if query else "")
        response = client.get(path)
        assert response.status_code == 302
        assert urlparse(response.headers["Location"]).path == route_url("login")

    def test_filter_is_not_preserved_across_login(self, client, demo_user_id):
        path = route_url("profile") + "?start=2026-10-01&end=2026-10-31"
        assert client.get(path).status_code == 302
        response = client.post(
            route_url("login"),
            data={"email": "demo@spendly.com", "password": "demo123"},
        )
        assert response.status_code == 302
        location = urlparse(response.headers["Location"])
        assert location.path == route_url("profile")
        assert location.query == "", "filter must not survive the login redirect"

    def test_logged_out_response_does_not_leak_profile_data(self, client, demo_user_id):
        response = client.get(route_url("profile") + "?start=2026-10-01")
        assert b"Demo User" not in response.data
        assert b"Total spent" not in response.data


# ------------------------------------------------------------------ #
# Default (All time) view                                             #
# ------------------------------------------------------------------ #

class TestDefaultView:
    def test_no_query_shows_all_time_seed_data(self, demo_client):
        markup = get_page(demo_client)
        assert stats(markup) == {"total": "₹401.50", "count": 8, "top": "Bills"}

    def test_no_query_selects_only_all_time(self, demo_client):
        assert selected_tabs(get_page(demo_client)) == ["All time"]

    def test_no_query_has_no_date_inputs_apply_clear_or_label(self, demo_client):
        markup = get_page(demo_client)
        text = to_text(markup)
        assert date_inputs(markup) == []
        assert "Apply" not in text
        assert "Clear" not in text
        assert "Showing" not in text

    def test_no_query_shows_four_tabs_in_order(self, demo_client):
        assert [t["label"] for t in tabs(get_page(demo_client))] == TAB_LABELS

    def test_all_time_tab_link_has_no_query_string(self, demo_client):
        href = tab_href(get_page(demo_client), "All time")
        parsed = urlparse(href)
        assert parsed.path == route_url("profile")
        assert parsed.query == ""

    def test_preset_tab_links_carry_expected_start_and_end(self, demo_client):
        markup = get_page(demo_client)
        today = date.today()
        this_month = parse_qs(urlparse(tab_href(markup, "This month")).query)
        assert this_month["start"] == [today.replace(day=1).isoformat()]
        assert this_month["end"] == [month_end(today).isoformat()]
        last3 = parse_qs(urlparse(tab_href(markup, "Last 3 months")).query)
        assert last3["start"] == [month_start_back(today, 2).isoformat()]
        assert last3["end"] == [month_end(today).isoformat()]
        for label in ("This month", "Last 3 months"):
            assert urlparse(tab_href(markup, label)).path == route_url("profile")

    def test_unfiltered_empty_user_does_not_show_filtered_empty_messages(self, empty_client):
        text = to_text(get_page(empty_client))
        assert "No transactions in this date range." not in text
        assert "No spending in this date range." not in text

    def test_unknown_range_value_has_no_effect(self, demo_client):
        markup = get_page(demo_client, "range=bogus")
        assert selected_tabs(markup) == ["All time"]
        assert stats(markup)["total"] == "₹401.50"


# ------------------------------------------------------------------ #
# Quick-select tabs                                                   #
# ------------------------------------------------------------------ #

class TestQuickSelectTabs:
    def _preset_query(self, label):
        today = date.today()
        if label == "This month":
            return f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}"
        return f"start={month_start_back(today, 2).isoformat()}&end={month_end(today).isoformat()}"

    def test_all_time_includes_every_expense(self, relative_client):
        markup = get_page(relative_client)
        assert stats(markup) == {"total": "₹150.00", "count": 5, "top": "Shopping"}

    def test_this_month_filters_stats_list_and_breakdown_together(self, relative_client):
        markup = get_page(relative_client, self._preset_query("This month"))
        assert stats(markup) == {"total": "₹30.00", "count": 2, "top": "Bills"}
        txns = transactions_text(markup)
        assert "cur-first" in txns and "cur-last" in txns
        for outside in ("prev-last", "two-first", "three-last"):
            assert outside not in txns
        cats = breakdown_text(markup)
        assert "Food" in cats and "Bills" in cats
        for outside in ("Health", "Transport", "Shopping"):
            assert outside not in cats

    def test_last_3_months_filters_stats_list_and_breakdown_together(self, relative_client):
        markup = get_page(relative_client, self._preset_query("Last 3 months"))
        assert stats(markup) == {"total": "₹100.00", "count": 4, "top": "Transport"}
        txns = transactions_text(markup)
        for inside in ("cur-first", "cur-last", "prev-last", "two-first"):
            assert inside in txns
        assert "three-last" not in txns
        cats = breakdown_text(markup)
        assert "Shopping" not in cats
        for inside in ("Food", "Bills", "Health", "Transport"):
            assert inside in cats

    @pytest.mark.parametrize("label", ["This month", "Last 3 months"])
    def test_preset_selects_only_its_tab(self, relative_client, label):
        markup = get_page(relative_client, self._preset_query(label))
        assert selected_tabs(markup) == [label]

    @pytest.mark.parametrize("label", ["This month", "Last 3 months"])
    def test_preset_shows_label_and_no_date_inputs_or_apply(self, relative_client, label):
        markup = get_page(relative_client, self._preset_query(label))
        text = to_text(markup)
        today = date.today()
        start = today.replace(day=1) if label == "This month" else month_start_back(today, 2)
        assert range_label(start, month_end(today)).search(text), f"expected a Showing label in: {text[:400]}"
        assert date_inputs(markup) == []
        assert "Apply" not in text

    @pytest.mark.parametrize("label", ["This month", "Last 3 months"])
    def test_following_the_tab_link_applies_the_preset(self, relative_client, label):
        base = get_page(relative_client)
        href = tab_href(base, label)
        response = relative_client.get(href)
        assert response.status_code == 200
        markup = response.get_data(as_text=True)
        assert selected_tabs(markup) == [label]
        expected = get_page(relative_client, self._preset_query(label))
        assert stats(markup) == stats(expected)

    def test_all_time_link_returns_to_unfiltered_data(self, relative_client):
        filtered = get_page(relative_client, self._preset_query("This month"))
        markup = relative_client.get(tab_href(filtered, "All time")).get_data(as_text=True)
        assert selected_tabs(markup) == ["All time"]
        assert stats(markup)["count"] == 5
        assert date_inputs(markup) == []

    def test_preset_dates_without_range_param_select_the_preset_tab(self, relative_client):
        markup = get_page(relative_client, self._preset_query("This month"))
        assert selected_tabs(markup) == ["This month"]

    def test_preset_excludes_expense_one_day_before_range(self, relative_client):
        markup = get_page(relative_client, self._preset_query("This month"))
        assert "prev-last" not in transactions_text(markup)

    def test_filtered_percentages_sum_to_100_in_page(self, empty_client, empty_user_id):
        for cat in ("Food", "Bills", "Health"):
            add_expense(empty_user_id, 10.0, cat, "2020-06-10", cat + "-item")
        markup = get_page(empty_client, "start=2020-06-01&end=2020-06-30&range=custom")
        pcts = [int(p) for p in re.findall(r"(\d+)%", breakdown_text(markup))]
        assert len(pcts) == 3
        assert sum(pcts) == 100


# ------------------------------------------------------------------ #
# Custom tab                                                          #
# ------------------------------------------------------------------ #

class TestCustomTab:
    def test_custom_selects_only_custom_tab(self, demo_client):
        assert selected_tabs(get_page(demo_client, "range=custom")) == ["Custom"]

    def test_custom_shows_from_to_inputs_and_apply(self, demo_client):
        markup = get_page(demo_client, "range=custom")
        text = to_text(markup)
        fields = date_inputs(markup)
        assert sorted(f.get("name") for f in fields) == ["end", "start"]
        assert re.search(r"<label\b[^>]*>\s*From\s*</label>", markup), "expected a 'From' label"
        assert re.search(r"<label\b[^>]*>\s*To\s*</label>", markup), "expected a 'To' label"
        assert "Apply" in text

    def test_custom_form_is_a_get_form_posting_to_profile(self, demo_client):
        markup = get_page(demo_client, "range=custom")
        forms = [
            attrs
            for attrs, body in re.findall(r"<form\b([^>]*)>(.*?)</form>", markup, flags=re.S)
            if 'type="date"' in body
        ]
        assert len(forms) == 1, "expected exactly one form wrapping the date inputs"
        assert 'method="get"' in forms[0].lower()
        assert f'action="{route_url("profile")}"' in forms[0]

    def test_custom_form_has_hidden_range_custom_field(self, demo_client):
        markup = get_page(demo_client, "range=custom")
        hidden = [i for i in inputs(markup) if i.get("name") == "range"]
        assert hidden and hidden[0].get("type") == "hidden"
        assert hidden[0].get("value") == "custom"

    def test_custom_alone_leaves_data_unfiltered_and_inputs_empty(self, demo_client):
        markup = get_page(demo_client, "range=custom")
        assert stats(markup) == {"total": "₹401.50", "count": 8, "top": "Bills"}
        assert all(f.get("value", "") == "" for f in date_inputs(markup))
        assert "Showing" not in to_text(markup)

    def test_custom_alone_does_not_show_clear(self, demo_client):
        assert "Clear" not in to_text(get_page(demo_client, "range=custom"))

    def test_custom_tab_link_without_filter_is_range_custom_only(self, demo_client):
        href = tab_href(get_page(demo_client), "Custom")
        parsed = urlparse(href)
        assert parsed.path == route_url("profile")
        assert parse_qs(parsed.query) == {"range": ["custom"]}

    @pytest.mark.parametrize("label", ["This month", "Last 3 months"])
    def test_custom_link_from_preset_carries_range_and_prefills_inputs(self, relative_client, label):
        today = date.today()
        start = today.replace(day=1) if label == "This month" else month_start_back(today, 2)
        end = month_end(today)
        page = get_page(relative_client, f"start={start.isoformat()}&end={end.isoformat()}")
        href = tab_href(page, "Custom")
        query = parse_qs(urlparse(href).query)
        assert query["range"] == ["custom"]
        assert query["start"] == [start.isoformat()]
        assert query["end"] == [end.isoformat()]

        markup = relative_client.get(href).get_data(as_text=True)
        assert selected_tabs(markup) == ["Custom"]
        values = {f["name"]: f.get("value", "") for f in date_inputs(markup)}
        assert values == {"start": start.isoformat(), "end": end.isoformat()}
        assert stats(markup) == stats(page), "clicking Custom keeps the active range's data"

    def test_range_custom_with_preset_dates_keeps_custom_selected(self, relative_client):
        today = date.today()
        query = (
            f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}"
            "&range=custom"
        )
        markup = get_page(relative_client, query)
        assert selected_tabs(markup) == ["Custom"], "no quick-select tab may be selected"
        assert len(date_inputs(markup)) == 2
        assert stats(markup)["count"] == 2, "data is still filtered to the dates"

    def test_range_param_never_changes_the_data(self, dated_client):
        plain = get_page(dated_client, "start=2020-02-01&end=2020-02-29")
        custom = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        assert stats(plain) == stats(custom)
        assert transactions_text(plain) == transactions_text(custom)
        assert breakdown_text(plain) == breakdown_text(custom)

    def test_direct_dates_matching_no_preset_select_custom_and_show_inputs(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-15")
        assert selected_tabs(markup) == ["Custom"]
        values = {f["name"]: f.get("value", "") for f in date_inputs(markup)}
        assert values == {"start": "2020-02-01", "end": "2020-02-15"}

    def test_applied_custom_range_updates_every_section(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        assert stats(markup) == {"total": "₹160.00", "count": 3, "top": "Bills"}
        txns = transactions_text(markup)
        for inside in ("feb-start", "feb-mid", "feb-last"):
            assert inside in txns
        for outside in ("jan-end", "mar-first"):
            assert outside not in txns
        cats = breakdown_text(markup)
        for inside in ("Bills", "Health", "Food"):
            assert inside in cats
        assert "₹100.00" in cats and "₹40.00" in cats and "₹20.00" in cats

    def test_applied_custom_range_stays_on_custom_with_filled_inputs(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        assert selected_tabs(markup) == ["Custom"]
        values = {f["name"]: f.get("value", "") for f in date_inputs(markup)}
        assert values == {"start": "2020-02-01", "end": "2020-02-29"}

    def test_applied_custom_range_shows_label(self, dated_client):
        text = to_text(get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom"))
        assert range_label(date(2020, 2, 1), date(2020, 2, 29)).search(text), text[:400]

    def test_partial_range_of_seed_data_updates_all_sections(self, demo_client):
        today = date.today()
        start, end = today.replace(day=10), today.replace(day=20)
        markup = get_page(demo_client, f"start={start.isoformat()}&end={end.isoformat()}&range=custom")
        assert stats(markup) == {"total": "₹160.25", "count": 3, "top": "Shopping"}
        txns = transactions_text(markup)
        for inside in ("Concert tickets", "Shoes", "Gift"):
            assert inside in txns
        for outside in ("Groceries", "Bus pass top-up", "Electricity bill", "Pharmacy", "Dinner out"):
            assert outside not in txns
        cats = breakdown_text(markup)
        assert "Shopping" in cats and "Entertainment" in cats and "Other" in cats
        assert "Bills" not in cats and "Food" not in cats
        assert selected_tabs(markup) == ["Custom"]


# ------------------------------------------------------------------ #
# One-sided and inclusive ranges                                      #
# ------------------------------------------------------------------ #

class TestOneSidedAndInclusive:
    def test_start_only_excludes_earlier_expenses(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-15")
        assert stats(markup)["count"] == 3
        txns = transactions_text(markup)
        assert "feb-mid" in txns and "feb-last" in txns and "mar-first" in txns
        assert "feb-start" not in txns and "jan-end" not in txns

    def test_end_only_excludes_later_expenses(self, dated_client):
        markup = get_page(dated_client, "end=2020-02-01")
        assert stats(markup)["count"] == 2
        txns = transactions_text(markup)
        assert "jan-end" in txns and "feb-start" in txns
        assert "feb-mid" not in txns and "mar-first" not in txns

    def test_start_only_label_reads_showing_from(self, dated_client):
        text = to_text(get_page(dated_client, "start=2020-02-15"))
        assert re.search(r"Showing\s+from\s+15 Feb", text), text[:400]

    def test_end_only_label_reads_showing_up_to(self, dated_client):
        text = to_text(get_page(dated_client, "end=2020-02-29"))
        assert re.search(r"Showing\s+up\s+to\s+29 Feb", text), text[:400]

    def test_one_sided_range_selects_custom_and_shows_inputs(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-15")
        assert selected_tabs(markup) == ["Custom"]
        values = {f["name"]: f.get("value", "") for f in date_inputs(markup)}
        assert values == {"start": "2020-02-15", "end": ""}

    def test_expense_on_start_date_is_included(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-14")
        assert "feb-start" in transactions_text(markup)

    def test_expense_on_end_date_is_included(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-02&end=2020-02-29")
        assert "feb-last" in transactions_text(markup)

    def test_single_day_range_includes_only_that_day(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-15&end=2020-02-15")
        assert stats(markup) == {"total": "₹100.00", "count": 1, "top": "Bills"}

    def test_blank_start_with_valid_end_is_one_sided(self, dated_client):
        markup = get_page(dated_client, "start=&end=2020-02-01")
        assert stats(markup)["count"] == 2
        assert "Showing" in to_text(markup)

    def test_no_label_when_nothing_is_filtered(self, dated_client):
        assert "Showing" not in to_text(get_page(dated_client))


# ------------------------------------------------------------------ #
# Clear link                                                          #
# ------------------------------------------------------------------ #

class TestClearLink:
    def _clear_href(self, markup):
        for attrs, inner in re.findall(r"<a\b([^>]*)>(.*?)</a>", markup, flags=re.S):
            if to_text(inner) == "Clear":
                return html_lib.unescape(re.search(r'href="([^"]*)"', attrs).group(1))
        return None

    def test_clear_shown_when_custom_range_applied(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        assert self._clear_href(markup) is not None

    def test_clear_shown_for_one_sided_range(self, dated_client):
        assert self._clear_href(get_page(dated_client, "end=2020-02-01")) is not None

    def test_clear_not_shown_without_filter(self, dated_client):
        assert self._clear_href(get_page(dated_client, "range=custom")) is None
        assert self._clear_href(get_page(dated_client)) is None

    def test_clear_not_shown_on_preset_tabs(self, relative_client):
        today = date.today()
        query = f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}"
        assert self._clear_href(get_page(relative_client, query)) is None

    def test_clear_points_to_profile_range_custom_only(self, dated_client):
        href = self._clear_href(get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom"))
        parsed = urlparse(href)
        assert parsed.path == route_url("profile")
        assert parse_qs(parsed.query, keep_blank_values=True) == {"range": ["custom"]}

    def test_following_clear_resets_to_empty_custom_view(self, dated_client, dated_user_id):
        filtered = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        markup = dated_client.get(self._clear_href(filtered)).get_data(as_text=True)
        assert selected_tabs(markup) == ["Custom"]
        fields = date_inputs(markup)
        assert len(fields) == 2
        assert all(f.get("value", "") == "" for f in fields), "inputs must be empty after Clear"
        assert "Showing" not in to_text(markup)
        assert stats(markup) == {"total": "₹175.00", "count": 5, "top": "Bills"}
        assert self._clear_href(markup) is None


# ------------------------------------------------------------------ #
# Empty ranges and users with no data                                 #
# ------------------------------------------------------------------ #

class TestEmptyStates:
    def test_range_without_matches_shows_zero_dash_and_messages(self, dated_client):
        markup = get_page(dated_client, "start=2021-01-01&end=2021-12-31&range=custom")
        assert stats(markup) == {"total": "₹0.00", "count": 0, "top": "—"}
        text = to_text(markup)
        assert "No transactions in this date range." in text
        assert "No spending in this date range." in text

    def test_range_without_matches_shows_label_and_no_error_status(self, dated_client):
        response = dated_client.get(
            route_url("profile") + "?start=2021-01-01&end=2021-12-31"
        )
        assert response.status_code == 200
        assert "Showing" in to_text(response.get_data(as_text=True))

    def test_new_user_can_use_every_tab(self, empty_client):
        today = date.today()
        queries_to_try = [
            "",
            f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}",
            f"start={month_start_back(today, 2).isoformat()}&end={month_end(today).isoformat()}",
            "range=custom",
        ]
        for query in queries_to_try:
            markup = get_page(empty_client, query)
            assert stats(markup) == {"total": "₹0.00", "count": 0, "top": "—"}, query

    def test_new_user_can_apply_custom_range(self, empty_client):
        markup = get_page(empty_client, "start=2020-01-01&end=2020-12-31&range=custom")
        assert stats(markup)["count"] == 0
        assert selected_tabs(markup) == ["Custom"]
        assert "No transactions in this date range." in to_text(markup)

    def test_new_user_one_sided_ranges_do_not_error(self, empty_client):
        for query in ("start=2020-01-01", "end=2020-01-01"):
            get_page(empty_client, query)


# ------------------------------------------------------------------ #
# Validation errors                                                   #
# ------------------------------------------------------------------ #

INVALID_QUERIES = [
    "start=not-a-date",
    "end=2026-13-45",
    "start=2020-02-30",
    "start=2020-02-20&end=2020-02-01",
    "start=2020-02-15&end=garbage",
    "start=garbage&end=2020-02-15",
    "start=%27+OR+1%3D1+--",
    "end=2020-02-29%27%3B+DROP+TABLE+expenses%3B--",
]


class TestValidation:
    @pytest.mark.parametrize("query", INVALID_QUERIES)
    def test_invalid_range_does_not_error(self, dated_client, query):
        response = dated_client.get(route_url("profile") + f"?{query}")
        assert response.status_code == 200, f"{query} must not cause {response.status_code}"

    @pytest.mark.parametrize("query", INVALID_QUERIES)
    def test_invalid_range_shows_an_inline_error_message(self, dated_client, query):
        markup = get_page(dated_client, query)
        baseline = get_page(dated_client, "range=custom")
        extra = words(markup) - words(baseline)
        assert extra, f"expected an inline error message to be rendered for {query}"

    @pytest.mark.parametrize("query", INVALID_QUERIES)
    def test_invalid_range_falls_back_to_unfiltered_data(self, dated_client, query):
        markup = get_page(dated_client, query)
        assert stats(markup) == {"total": "₹175.00", "count": 5, "top": "Bills"}
        assert "Showing" not in to_text(markup)
        assert "Clear" not in to_text(markup)

    @pytest.mark.parametrize("query", INVALID_QUERIES)
    def test_invalid_range_selects_custom_and_shows_empty_inputs(self, dated_client, query):
        markup = get_page(dated_client, query)
        assert selected_tabs(markup) == ["Custom"]
        fields = date_inputs(markup)
        assert len(fields) == 2
        assert all(f.get("value", "") == "" for f in fields), "both bounds are dropped on error"

    def test_start_after_end_is_rejected_even_with_matching_data(self, dated_client):
        markup = get_page(dated_client, "start=2020-03-01&end=2020-01-31")
        assert stats(markup)["count"] == 5

    def test_start_equal_to_end_is_valid_and_not_an_error(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-15&end=2020-02-15")
        assert stats(markup)["count"] == 1, "data is filtered, not reverted"
        assert "Showing" in to_text(markup)

    @pytest.mark.parametrize("query", ["start=&end=", "start=", "end=", "start=&end=&range="])
    def test_blank_values_are_no_filter_and_no_error(self, dated_client, query):
        plain = get_page(dated_client)
        markup = get_page(dated_client, query)
        assert to_text(markup) == to_text(plain), "blank values must render like plain /profile"
        assert selected_tabs(markup) == ["All time"]
        assert date_inputs(markup) == []

    def test_blank_values_with_range_custom_show_inputs_without_error(self, dated_client):
        markup = get_page(dated_client, "start=&end=&range=custom")
        baseline = get_page(dated_client, "range=custom")
        assert to_text(markup) == to_text(baseline)
        assert selected_tabs(markup) == ["Custom"]

    def test_valid_dates_show_no_error_text(self, dated_client):
        valid = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        invalid = get_page(dated_client, "start=bad&range=custom")
        assert words(invalid) - words(valid), "only the invalid page should carry an error"


# ------------------------------------------------------------------ #
# Data isolation between users                                        #
# ------------------------------------------------------------------ #

class TestUserIsolation:
    def test_other_users_expenses_never_appear_in_custom_range(self, dated_client):
        markup = get_page(dated_client, "start=2020-02-01&end=2020-02-29&range=custom")
        text = to_text(markup)
        assert "OtherSecret" not in text
        assert "999" not in text
        assert stats(markup)["total"] == "₹160.00"
        assert "Shopping" not in breakdown_text(markup)

    def test_other_users_expenses_never_appear_in_this_month(self, relative_client):
        today = date.today()
        query = f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}"
        text = to_text(get_page(relative_client, query))
        assert "OtherToday" not in text
        assert "888" not in text

    def test_open_ended_range_does_not_expose_other_users(self, dated_client):
        markup = get_page(dated_client, "start=2000-01-01")
        assert "OtherSecret" not in markup and "OtherToday" not in markup
        assert stats(markup)["count"] == 5

    def test_demo_user_filter_ignores_new_users_expenses(self, demo_client, empty_user_id):
        add_expense(empty_user_id, 5000.0, "Other", date.today().isoformat(), "NotYours")
        markup = get_page(demo_client, "start=2000-01-01&end=2100-01-01&range=custom")
        assert "NotYours" not in markup
        assert stats(markup)["total"] == "₹401.50"

    def test_sql_injection_in_query_does_not_leak_other_users(self, dated_client):
        markup = get_page(dated_client, "start=%27+OR+%271%27%3D%271")
        assert "OtherSecret" not in markup and "OtherToday" not in markup
        assert stats(markup)["count"] == 5


# ------------------------------------------------------------------ #
# Exactly one tab is selected                                         #
# ------------------------------------------------------------------ #

class TestSingleSelectedTab:
    @pytest.mark.parametrize(
        "query, expected",
        [
            ("", "All time"),
            ("range=custom", "Custom"),
            ("start=2020-02-01&end=2020-02-10", "Custom"),
            ("start=2020-02-01", "Custom"),
            ("end=2020-02-10", "Custom"),
            ("start=2020-02-01&end=2020-02-10&range=custom", "Custom"),
            ("start=bad", "Custom"),
            ("start=2020-03-01&end=2020-01-01", "Custom"),
            ("start=&end=", "All time"),
        ],
    )
    def test_exactly_one_tab_selected(self, dated_client, query, expected):
        assert selected_tabs(get_page(dated_client, query)) == [expected]

    def test_exactly_one_tab_selected_for_every_preset(self, dated_client):
        today = date.today()
        cases = {
            "This month": f"start={today.replace(day=1).isoformat()}&end={month_end(today).isoformat()}",
            "Last 3 months": f"start={month_start_back(today, 2).isoformat()}&end={month_end(today).isoformat()}",
        }
        for label, query in cases.items():
            assert selected_tabs(get_page(dated_client, query)) == [label]
