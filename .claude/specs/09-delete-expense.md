# Spec: Delete Expense

## Overview
Step 9 lets a logged-in user permanently delete one of their own expenses. The
stub at `/expenses/<int:id>/delete` is replaced with a two-step flow: a GET
renders a confirmation page showing the expense's details, and a POST performs
the deletion and redirects to `/profile` with a success flash. The deletion is
deliberately POST-only so that a link prefetch, crawler or cross-site image tag
can never remove data, and the confirmation page needs no JavaScript. Ownership
is enforced: a user can only delete expenses that belong to them. This completes
the add / edit / delete expense CRUD set that began in Steps 7 and 8.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the delete link lives there)
- Step 7: Add Expense (flash message pattern on `/profile`)
- Step 8: Edit Expense (`get_expense_by_id`, per-row Actions column, 404 on
  missing or foreign expense)

## Routes
- `GET /expenses/<int:id>/delete` — render a confirmation page for the expense
  (amount, category, date, description) with "Delete" and "Cancel" actions —
  logged-in only
- `POST /expenses/<int:id>/delete` — delete the expense, flash a success
  message, redirect to `/profile` — logged-in only

Both methods redirect to `/login` when logged out, and return 404 when the
expense does not exist or belongs to another user. The existing route function
name `delete_expense` is kept, so `url_for('delete_expense', id=...)` works.

## Database changes
No database changes. The existing `expenses` table is sufficient. Verified
against `database/db.py`: `expenses.user_id` references `users(id)` and nothing
references `expenses`, so deleting a row cannot violate a foreign key.

## Templates
- **Create:** `templates/delete_expense.html`
  - Extends `base.html`; reuses the `auth-section` / `auth-card` layout from
    `edit_expense.html`
  - Heading "Delete expense" and a warning line that the action cannot be undone
  - A read-only summary of the expense: amount (`| inr`), category, date
    (`| short_date`), description (or "No description")
  - `<form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}">`
    with a danger-styled "Delete" submit button and a "Cancel" link to
    `url_for('profile')`
- **Modify:** `templates/profile.html`
  - In each transaction row's `txn-actions` cell, add a "Delete" link next to
    "Edit" pointing to `url_for('delete_expense', id=t.id)`

## Files to change
- `database/db.py`
  - Add `remove_expense(expense_id, user_id)` — parameterised
    `DELETE FROM expenses WHERE id = ? AND user_id = ?`; commit; return `True`
    if a row was removed. It is named `remove_expense`, not `delete_expense`,
    so it does not collide with the route function of that name in `app.py`.
- `app.py`
  - Import `remove_expense` from `database.db`
  - Replace the stub body at `/expenses/<int:id>/delete` with a handler that
    accepts `methods=["GET", "POST"]`:
    - logged out → `redirect(url_for("login"))`
    - `get_expense_by_id(id, session["user_id"])` is `None` → `abort(404)`
    - GET → render `delete_expense.html` with `expense`
    - POST → `remove_expense(id, session["user_id"])`; `abort(404)` if it
      returns `False`; flash `"Expense deleted: ₹… · Category · DD Mon"` (same
      format as the add/edit messages, plus description when present) with
      category `"success"`; `redirect(url_for("profile"))`
- `templates/profile.html` — add the per-row "Delete" link (see above)
- `static/css/style.css` — add a `.btn-danger` button style built from the
  `--danger` / `--danger-light` variables, and any small spacing rule needed so
  Edit and Delete sit side by side in `.txn-actions` (including the mobile grid
  layout)
- `CLAUDE.md` — change the `GET /expenses/<id>/delete` row in the route table
  from "Stub — Step 9" to Implemented, and update the Overview / Architecture
  text that still calls delete a stub

## Files to create
- `templates/delete_expense.html` — the confirmation page
- `tests/test_09-delete-expense.py` — written later via `/test-feature`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (no password handling changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles and no inline `<style>` tags
- Deletion must happen only on POST; a GET must never modify data
- `remove_expense` must scope its `WHERE` to both `id` and `user_id`
  (ownership guard); the route also pre-checks with `get_expense_by_id`
- DB logic stays in `database/db.py`; the route only checks the session, fetches,
  renders or redirects
- Use `abort(404)` for a missing or foreign expense, not a returned string
- Use `url_for()` for every link and form action — no hardcoded URLs
- Do not add JavaScript; the confirmation is a server-rendered page
- Currency displays as ₹ via the existing `inr` filter
- Keep the app on port 5001 and do not touch the add/edit routes beyond the
  import line

## Definition of done
- [ ] While logged out, `GET` and `POST` to `/expenses/<id>/delete` redirect to `/login`
- [ ] Logged in, `/expenses/<id>/delete` for a non-existent id returns 404 (GET and POST)
- [ ] Logged in, `/expenses/<id>/delete` for another user's expense returns 404 (GET and POST), and that expense is still in the database
- [ ] Each row in the profile transactions table shows both "Edit" and "Delete" links, and "Delete" points to the correct `/expenses/<id>/delete`
- [ ] Clicking "Delete" opens a confirmation page showing that expense's amount (in ₹), category, date and description
- [ ] Opening the confirmation page (GET) does not delete anything
- [ ] "Cancel" on the confirmation page returns to `/profile` and the expense is still listed
- [ ] Confirming redirects to `/profile`, the expense no longer appears in the transactions table, and a "Expense deleted: …" success message is shown
- [ ] After a deletion the stat tiles (total spent, transaction count, top category) and the category breakdown reflect the removal
- [ ] Deleting the user's last expense shows the "No transactions yet." empty state
- [ ] Reloading `/profile` after deleting does not show the flash message again
- [ ] Re-submitting the delete for an already-deleted id returns 404
- [ ] The Delete button is visibly styled as destructive, and the Edit/Delete links fit in the Actions column on a narrow (mobile) viewport
- [ ] The `CLAUDE.md` route table lists `/expenses/<id>/delete` as implemented
