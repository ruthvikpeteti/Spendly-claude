import pytest

from database import db, queries
from tests.conftest import login

# Fixed dates for a throwaway user, so the tests never depend on the
# month-relative seed data.
EXPENSES = [
    ("2026-09-30", "Food", 10.00, "Before range"),
    ("2026-10-01", "Food", 20.00, "On start"),
    ("2026-10-10", "Bills", 50.00, "Middle"),
    ("2026-10-15", "Transport", 30.00, "On end"),
    ("2026-10-16", "Shopping", 40.00, "After range"),
]


@pytest.fixture
def user_id(empty_user_id):
    conn = db.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(empty_user_id, amt, cat, day, desc) for day, cat, amt, desc in EXPENSES],
        )
        conn.commit()
    finally:
        conn.close()
    return empty_user_id


@pytest.fixture
def logged_in(client, user_id):
    login(client, user_id, "Empty User")
    return client


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

def test_stats_no_bounds_covers_everything(user_id):
    stats = queries.get_summary_stats(user_id)
    assert stats["transaction_count"] == 5
    assert stats["total_spent"] == 150.00


def test_stats_both_bounds_are_inclusive(user_id):
    stats = queries.get_summary_stats(user_id, "2026-10-01", "2026-10-15")
    assert stats["transaction_count"] == 3
    assert stats["total_spent"] == 100.00
    assert stats["top_category"] == "Bills"


def test_stats_start_only(user_id):
    stats = queries.get_summary_stats(user_id, start_date="2026-10-10")
    assert stats["transaction_count"] == 3
    assert stats["total_spent"] == 120.00


def test_stats_end_only(user_id):
    stats = queries.get_summary_stats(user_id, end_date="2026-10-01")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == 30.00


def test_stats_empty_range(user_id):
    stats = queries.get_summary_stats(user_id, "2030-01-01", "2030-12-31")
    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


def test_transactions_filtered_newest_first(user_id):
    rows = queries.get_recent_transactions(
        user_id, start_date="2026-10-01", end_date="2026-10-15"
    )
    assert [r["description"] for r in rows] == ["On end", "Middle", "On start"]


def test_transactions_limit_applies_inside_range(user_id):
    rows = queries.get_recent_transactions(
        user_id, limit=2, start_date="2026-10-01", end_date="2026-10-15"
    )
    assert [r["description"] for r in rows] == ["On end", "Middle"]


def test_transactions_empty_range(user_id):
    assert queries.get_recent_transactions(
        user_id, start_date="2030-01-01"
    ) == []


def test_breakdown_filtered_and_sums_to_100(user_id):
    breakdown = queries.get_category_breakdown(user_id, "2026-10-01", "2026-10-15")
    assert [c["name"] for c in breakdown] == ["Bills", "Transport", "Food"]
    assert sum(c["amount"] for c in breakdown) == 100.00
    assert sum(c["pct"] for c in breakdown) == 100


def test_breakdown_empty_range(user_id):
    assert queries.get_category_breakdown(user_id, end_date="2000-01-01") == []


def test_filter_never_returns_another_users_rows(user_id, demo_user_id):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_user_id, 999.00, "Other", "2026-10-05", "Demo only"),
        )
        conn.commit()
    finally:
        conn.close()

    rows = queries.get_recent_transactions(
        user_id, start_date="2026-10-01", end_date="2026-10-15"
    )
    assert "Demo only" not in {r["description"] for r in rows}
    stats = queries.get_summary_stats(user_id, "2026-10-01", "2026-10-15")
    assert stats["total_spent"] == 100.00


# ------------------------------------------------------------------ #
# Route                                                               #
# ------------------------------------------------------------------ #

def test_profile_filter_redirects_when_logged_out(client):
    response = client.get("/profile?start=2026-10-01")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_unfiltered_shows_all_and_no_clear_link(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "₹150.00" in html
    assert "Before range" in html and "After range" in html
    assert ">Clear<" not in html
    assert "Showing" not in html


def test_profile_filter_updates_all_sections(logged_in):
    html = logged_in.get(
        "/profile?start=2026-10-01&end=2026-10-15"
    ).get_data(as_text=True)
    assert "₹100.00" in html
    assert "On start" in html and "On end" in html and "Middle" in html
    assert "Before range" not in html and "After range" not in html
    assert "Shopping" not in html


def test_profile_filter_prefills_inputs_and_shows_label(logged_in):
    html = logged_in.get(
        "/profile?start=2026-10-01&end=2026-10-15"
    ).get_data(as_text=True)
    assert 'value="2026-10-01"' in html
    assert 'value="2026-10-15"' in html
    assert "Showing 01 Oct – 15 Oct" in html
    assert ">Clear<" in html


def test_profile_one_sided_filter(logged_in):
    html = logged_in.get("/profile?start=2026-10-10").get_data(as_text=True)
    assert "Showing from 10 Oct" in html
    assert "Before range" not in html and "On start" not in html
    assert "After range" in html


def test_profile_empty_range_shows_filtered_empty_states(logged_in):
    response = logged_in.get("/profile?start=2030-01-01&end=2030-12-31")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₹0.00" in html
    assert "No transactions in this date range." in html
    assert "No spending in this date range." in html


@pytest.mark.parametrize(
    "query, message",
    [
        ("start=not-a-date", "Enter dates as YYYY-MM-DD."),
        ("end=2026-13-45", "Enter dates as YYYY-MM-DD."),
        ("start=2026-10-20&end=2026-10-01", "Start date must be on or before end date."),
    ],
)
def test_profile_invalid_range_shows_error_and_unfiltered_data(logged_in, query, message):
    response = logged_in.get(f"/profile?{query}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert message in html
    assert "₹150.00" in html
    assert ">Clear<" not in html


def test_profile_blank_params_are_treated_as_no_filter(logged_in):
    html = logged_in.get("/profile?start=&end=").get_data(as_text=True)
    assert "₹150.00" in html
    assert 'class="filter-error"' not in html


def test_profile_filter_works_for_user_without_expenses(client, empty_user_id):
    login(client, empty_user_id, "Empty User")
    response = client.get("/profile?start=2026-10-01&end=2026-10-15")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₹0.00" in html
    assert "No transactions in this date range." in html


# ------------------------------------------------------------------ #
# Quick-select presets                                                #
# ------------------------------------------------------------------ #

def test_date_presets_mid_year():
    from datetime import date
    from app import date_presets

    presets = {p["label"]: p for p in date_presets(date(2026, 10, 22))}
    assert presets["All time"]["start"] is None and presets["All time"]["end"] is None
    assert (presets["This month"]["start"], presets["This month"]["end"]) == (
        "2026-10-01", "2026-10-31")
    assert (presets["Last 3 months"]["start"], presets["Last 3 months"]["end"]) == (
        "2026-08-01", "2026-10-31")


def test_date_presets_cross_year_and_leap_february():
    from datetime import date
    from app import date_presets

    jan = {p["label"]: p for p in date_presets(date(2026, 1, 15))}
    assert jan["Last 3 months"]["start"] == "2025-11-01"
    feb = {p["label"]: p for p in date_presets(date(2028, 2, 10))}
    assert feb["This month"]["end"] == "2028-02-29"
    assert feb["Last 3 months"]["start"] == "2027-12-01"


def _active_presets(html):
    import re

    return re.findall(r'is-active"[^>]*>([^<]+)</a>', html)


def test_profile_shows_presets_with_all_time_active_by_default(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    for label in ("All time", "This month", "Last 3 months", "Custom"):
        assert label in html
    assert _active_presets(html) == ["All time"]


def test_profile_marks_matching_preset_active(logged_in):
    from datetime import date
    from app import date_presets

    month = date_presets(date.today())[1]
    html = logged_in.get(
        f"/profile?start={month['start']}&end={month['end']}"
    ).get_data(as_text=True)
    assert _active_presets(html) == ["This month"]


def test_profile_custom_range_marks_only_custom_active(logged_in):
    html = logged_in.get(
        "/profile?start=2026-10-01&end=2026-10-15"
    ).get_data(as_text=True)
    assert _active_presets(html) == ["Custom"]


# ------------------------------------------------------------------ #
# Custom tab: date inputs appear only for custom ranges               #
# ------------------------------------------------------------------ #

def _has_date_inputs(html):
    return 'name="start"' in html and 'name="end"' in html


def test_date_inputs_hidden_by_default(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert not _has_date_inputs(html)
    assert "Apply" not in html


def test_date_inputs_hidden_for_each_preset(logged_in):
    from datetime import date
    from app import date_presets

    for preset in date_presets(date.today()):
        query = ""
        if preset["start"]:
            query = f"?start={preset['start']}&end={preset['end']}"
        html = logged_in.get(f"/profile{query}").get_data(as_text=True)
        assert not _has_date_inputs(html), preset["label"]
        assert _active_presets(html) == [preset["label"]]


def test_custom_tab_shows_inputs_and_is_only_active_tab(logged_in):
    html = logged_in.get("/profile?range=custom").get_data(as_text=True)
    assert _has_date_inputs(html)
    assert 'name="range" value="custom"' in html
    assert _active_presets(html) == ["Custom"]
    # Nothing is filtered until dates are applied.
    assert "₹150.00" in html


def test_custom_range_matching_a_preset_stays_in_custom_mode(logged_in):
    from datetime import date
    from app import date_presets

    month = date_presets(date.today())[1]
    html = logged_in.get(
        f"/profile?range=custom&start={month['start']}&end={month['end']}"
    ).get_data(as_text=True)
    assert _has_date_inputs(html)
    assert _active_presets(html) == ["Custom"]


def test_custom_range_without_range_param_shows_inputs(logged_in):
    html = logged_in.get(
        "/profile?start=2026-10-01&end=2026-10-15"
    ).get_data(as_text=True)
    assert _has_date_inputs(html)
    assert _active_presets(html) == ["Custom"]


def test_custom_tab_link_keeps_current_range(logged_in):
    from datetime import date
    from app import date_presets

    month = date_presets(date.today())[1]
    html = logged_in.get(
        f"/profile?start={month['start']}&end={month['end']}"
    ).get_data(as_text=True)
    assert f"range=custom&amp;start={month['start']}&amp;end={month['end']}" in html


def test_invalid_dates_reopen_custom_inputs(logged_in):
    html = logged_in.get("/profile?range=custom&start=bad").get_data(as_text=True)
    assert _has_date_inputs(html)
    assert "Enter dates as YYYY-MM-DD." in html
    assert _active_presets(html) == ["Custom"]


def test_range_label_shows_for_preset_filters_too(logged_in):
    from datetime import date
    from app import date_presets

    month = date_presets(date.today())[1]
    html = logged_in.get(
        f"/profile?start={month['start']}&end={month['end']}"
    ).get_data(as_text=True)
    assert "Showing" in html


def test_clear_link_stays_in_custom_mode_with_empty_dates(logged_in):
    html = logged_in.get(
        "/profile?range=custom&start=2026-10-01&end=2026-10-15"
    ).get_data(as_text=True)
    assert 'href="/profile?range=custom">Clear<' in html

    cleared = logged_in.get("/profile?range=custom").get_data(as_text=True)
    assert _has_date_inputs(cleared)
    assert _active_presets(cleared) == ["Custom"]
    assert 'value="2026-' not in cleared
    assert "₹150.00" in cleared
    assert "Showing" not in cleared
