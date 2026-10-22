# Spec: Date Filter for Profile Page

## Overview
Step 6 lets a logged-in user narrow the profile page to a date range. Today
`/profile` always shows all-time data: total spent, transaction count, top
category, the 10 most recent transactions and the category breakdown. This step
adds a date filter to the page: three quick-select tabs (**All time**,
**This month**, **Last 3 months**) and a fourth **Custom** tab that reveals
"from" and "to" date inputs. The chosen range is sent as query parameters on
`GET /profile` and applied to all three data sections together, so the stats,
transaction list and category breakdown always describe the same period. With
no range given, the page behaves exactly as it does now (All time).

## Depends on
- Step 1: Database setup (`expenses.date` is stored as ISO `YYYY-MM-DD` text)
- Step 3: Login / Logout (`session["user_id"]`)
- Step 4: Profile page UI
- Step 5: Profile backend (`database/queries.py` helpers already feed the page)

## Routes
No new routes. The existing `GET /profile` — logged-in — accepts these optional
query parameters:
- `start` — inclusive lower bound, `YYYY-MM-DD`
- `end` — inclusive upper bound, `YYYY-MM-DD`
- `range` — the only meaningful value is `custom`; it forces the Custom tab to
  be selected (and the date inputs to show) and has no effect on the data

Behaviour:
- Either or both of `start` / `end` may be given. A missing or empty value means "no bound" on that side.
- A value that is not a valid `YYYY-MM-DD` date is ignored, and the page shows an inline error message.
- If `start` is later than `end`, the filter is ignored and the page shows an inline error message.
- On any such error both bounds are dropped and the page shows unfiltered (all-time) data.
- Logged-out users are still redirected to `/login`; the filter is not preserved across login.

### Quick-select ranges
Computed from today's date on the server. Each tab is a plain link to
`/profile` with the matching `start` / `end` parameters:

| Tab | `start` | `end` |
|---|---|---|
| All time | none | none (link has no query string) |
| This month | 1st of the current month | last day of the current month |
| Last 3 months | 1st of the month two months before the current month | last day of the current month |

Examples for today = 2026-10-22: This month = 2026-10-01 – 2026-10-31;
Last 3 months = 2026-08-01 – 2026-10-31. Last 3 months must roll back over a
year boundary correctly (in January 2026 it starts 2025-11-01), and "This
month" must end on 2028-02-29 for February 2028.

### Which tab is selected
Exactly one tab is selected (highlighted and marked `aria-current="true"`):
- **Custom** is selected when `range=custom` is present, OR the dates were rejected (error), OR the applied `start`/`end` do not exactly equal any quick-select range.
- Otherwise the quick-select tab whose `start`/`end` exactly equal the applied range is selected (All time when no bounds are applied).
- If `range=custom` is present, no quick-select tab is selected even when the dates equal a quick-select range.

## Database changes
No database changes. `expenses.date` is already `TEXT NOT NULL` in ISO format,
so string comparison with `date >= ?` and `date <= ?` is correct. No index is
added; the table is small for this teaching project.

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter card above the stats tiles containing a row of four tabs, in order: **All time**, **This month**, **Last 3 months**, **Custom**. Tabs are links built with `url_for('profile', ...)`.
  - The **Custom** tab links to `/profile?range=custom` and carries the currently applied `start` / `end` along (when there are any), so the inputs are prefilled with the range the user was just viewing.
  - The date form (`method="get"`, `action="{{ url_for('profile') }}"`) is rendered **only while Custom is selected**. It has two `<input type="date">` fields (`start`, `end`) labelled "From" and "To", prefilled with the applied values, a hidden field `range=custom` so the page stays on Custom after Apply, and an Apply submit button.
  - When any filter is applied, the form also shows a **Clear** link. Clear goes to `/profile?range=custom`: the user stays on the Custom tab with **empty** date inputs and unfiltered data. (All time is the way back to the plain unfiltered view.) Clear is not shown when no filter is applied.
  - The date inputs and Apply button are **not present** in the page when All time, This month or Last 3 months is selected.
  - When a filter is applied — by a quick-select tab or by custom dates — show a short label of the range next to the tabs, e.g. "Showing 01 Oct – 31 Oct", "Showing from 10 Oct" (start only) or "Showing up to 18 Oct" (end only). No label when nothing is filtered.
  - Show the inline error message when the range was invalid.
  - Empty-state text for filtered results: "No transactions in this date range." and "No spending in this date range." Keep the existing empty-state text when no filter is active.
  - Stat tile label "Total spent" stays the same; no structural change to the existing sections.

## Files to change
- `app.py` — read and validate `start` / `end` in `profile()`, pass them to the query helpers, and pass `start`, `end`, `error`, `filtered`, the quick-select list (each with an `active` flag) and `custom_active` to the template. Add small helpers for parsing the range (`parse_date_range`) and building the quick-select ranges (`date_presets`).
- `database/queries.py` — add optional `start_date=None, end_date=None` parameters to `get_summary_stats`, `get_recent_transactions` and `get_category_breakdown`, and a shared private helper that builds the `AND date >= ? AND date <= ?` clause plus its parameter list.
- `templates/profile.html` — as described above.
- `static/css/style.css` — styles for the tabs, the form, the error message and the range label, near the other profile styles.

## Files to create
- `tests/test_date_filter.py` — query helper and route tests (see Definition of done for the cases).

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — the date bounds are passed as `?` parameters; the only text appended to SQL is the fixed clause strings, never user input
- Passwords hashed with werkzeug (unchanged; no auth code is touched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles and no inline `<style>` tags
- Vanilla JS only; the whole filter, including the Custom tab, must work with no JavaScript (plain links and a plain GET form)
- Use `url_for('profile', ...)` for every tab, the form action and the Clear link — never hardcode `/profile`
- Date validation uses `datetime.strptime(value, "%Y-%m-%d")`; the route passes only validated ISO strings (or `None`) to the query helpers
- Omitting both bounds must produce the same results as before this step; existing Step 5 tests must still pass without modification
- Filtering applies to all three sections (stats, transactions, breakdown) — never to only some of them
- `get_recent_transactions` still returns at most `limit` rows (default 10), newest first, within the range
- A user's filter can never expose another user's expenses; `user_id = ?` stays in every query
- The `range` parameter only controls which tab is shown; it must never change which expenses are returned
- Do not implement the add / edit / delete expense stubs
- Currency stays ₹ via the existing `inr` filter

## Definition of done
- [ ] Visiting `/profile` with no query string looks and behaves exactly as before (₹401.50 total, 8 transactions, "Bills" on the seed account), with the **All time** tab selected and no date inputs on the page
- [ ] The filter card shows four tabs in order: All time, This month, Last 3 months, Custom
- [ ] Selecting **This month** or **Last 3 months** filters all five data areas (total, count, top category, transaction list, category breakdown) to that range, highlights that tab, shows the "Showing …" label, and shows **no** date inputs or Apply button
- [ ] This month covers the 1st to the last day of the current month; Last 3 months covers the 1st of the month two months back to the last day of the current month (correct across a year boundary and for February in a leap year)
- [ ] Selecting **All time** shows unfiltered data and no date inputs
- [ ] Selecting **Custom** (`/profile?range=custom`) highlights only Custom and shows the "From" and "To" date inputs and an Apply button; data stays unfiltered until dates are applied
- [ ] Clicking Custom while a quick-select range is active keeps that range's data and prefills the From/To inputs with its dates
- [ ] Submitting a custom range that covers only part of the seed data updates the total, the transaction count, the top category, the transaction list and the category breakdown to match only that range, and the page stays on the Custom tab with the inputs still filled
- [ ] A custom range whose dates exactly equal a quick-select range still stays on the Custom tab when submitted from the form (`range=custom` present)
- [ ] Opening `/profile?start=2026-10-01&end=2026-10-15` directly (no `range` parameter, matching no quick-select range) selects Custom and shows the inputs
- [ ] Setting only `start` (e.g. `/profile?start=2026-10-10`) excludes earlier expenses; setting only `end` excludes later ones; the label reads "Showing from …" / "Showing up to …"
- [ ] The range is inclusive: an expense dated exactly on `start` or `end` is included
- [ ] The **Clear** link appears only while a filter is applied. Clicking it returns to `/profile?range=custom`: Custom is still selected, both date inputs are empty, no "Showing …" label is shown and data is unfiltered
- [ ] A range with no matching expenses shows ₹0.00, 0 transactions, "—" as top category and the filtered empty-state messages — no errors
- [ ] `/profile?start=not-a-date`, `/profile?end=2026-13-45` and `/profile?start=2026-10-20&end=2026-10-01` show an inline error and fall back to unfiltered data, with no 500 error; Custom is selected and the inputs are shown
- [ ] Blank values (`/profile?start=&end=`) are treated as no filter and show no error
- [ ] Category breakdown percentages within a filtered range still sum to 100
- [ ] A newly registered user with no expenses can use every tab and apply a custom range without errors
- [ ] Logged-out access to `/profile?start=2026-10-01` redirects to `/login`
- [ ] `pytest` passes, including tests for: each query helper with and without bounds, inclusive boundaries, empty range, another user's expenses never included, invalid date, start after end, the quick-select ranges (including year boundary and leap February), which tab is selected in each case, inputs shown only for Custom, Clear behaviour, and the unauthenticated redirect
