# Spec: Registration

## Overview

Make the existing registration page functional. Today `GET /register` only renders a static form whose `POST` has nowhere to go. This step adds the `POST /register` handler so a visitor can create a Spendly account: the submitted name, email and password are validated, the password is hashed with werkzeug, and a row is inserted into the `users` table created in Step 1. It is the first write path in the app and the prerequisite for login, logout and every logged-in page that follows.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, `init_db()` in `database/db.py`)

## Routes

- `GET /register` — render the empty registration form (already implemented, behaviour unchanged) — public
- `POST /register` — validate the form, create the user, redirect to `/login` on success; re-render the form with an error message on failure — public

Implement both methods on the existing `register` view function (`methods=["GET", "POST"]`). Do not rename the function; templates link to it via `url_for('register')`.

## Database changes

No database changes. The `users` table in `database/db.py` already has `name`, `email` (UNIQUE), `password_hash` and `created_at`.

New helper functions are added to `database/db.py` (no schema change):

- `create_user(name, email, password)` — hashes `password` with `generate_password_hash`, inserts the row with a parameterised query, commits, returns the new user id. Lets `sqlite3.IntegrityError` propagate for a duplicate email.
- `get_user_by_email(email)` — returns the matching `sqlite3.Row` or `None`.

Each helper opens its own connection with `get_db()` and closes it in a `finally` block, matching the existing helpers.

## Templates

- **Create:** none
- **Modify:** `templates/register.html`
  - Change the hardcoded `action="/register"` to `action="{{ url_for('register') }}"`
  - Re-populate the `name` and `email` inputs from the submitted values after a failed submit (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`); never re-populate the password

## Files to change

- `app.py` — import `request`, `redirect`, `url_for`; add `create_user` / `get_user_by_email` imports; extend the `register` view to handle `POST`
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — `url_for` action and value re-population

## Files to create

None.

## New dependencies

No new dependencies. `werkzeug.security` is already installed.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings or `%` formatting in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only; the route just reads the form, calls helpers and renders or redirects
- Never use a bare `return "string"` — render a template or redirect
- Use `url_for()` for every internal link and redirect — no hardcoded URLs
- Do not implement login, logout, sessions or `flask.session` — those belong to later steps. Registration does not log the user in.
- Do not touch the other stub routes (`/logout`, `/profile`, `/expenses/*`)
- Validation (server side, in this order), each failure re-renders `register.html` with an `error` string:
  - `name` and `email` are stripped; `name`, `email` and `password` must all be non-empty → "All fields are required."
  - `email` is lower-cased before checking or storing, and must contain `@` with text on both sides and a `.` in the domain → "Enter a valid email address."
  - `password` is at least 8 characters (matches the form placeholder) → "Password must be at least 8 characters."
  - email must not already exist → "An account with that email already exists."
- Check for a duplicate with `get_user_by_email()` for the friendly message, and also catch `sqlite3.IntegrityError` around `create_user()` so a race on the UNIQUE constraint does not produce a 500
- Reuse the existing `.auth-error` class for errors; add no new CSS unless strictly needed, and if so put it in `static/css/style.css` using the existing variables
- Do not change the port (5001)

## Definition of done

- [ ] `python app.py` starts on port 5001 without errors
- [ ] `GET /register` renders the form and the form's `action` resolves to `/register` via `url_for`
- [ ] Submitting valid name, email and an 8+ character password redirects to `/login`
- [ ] The new row appears in `users` with the correct name, a lower-cased email, and a `password_hash` starting with `scrypt:` or `pbkdf2:` (never the plain password)
- [ ] `created_at` is populated on the new row
- [ ] Registering the same email again (including with different letter case) shows "An account with that email already exists." and creates no second row
- [ ] Submitting with any empty field shows "All fields are required." and creates no row
- [ ] An email such as `foo` or `foo@bar` shows "Enter a valid email address."
- [ ] A 7-character password shows "Password must be at least 8 characters."
- [ ] After any failed submit the name and email fields keep their values and the password field is empty
- [ ] The existing demo user (`demo@spendly.com`) is untouched
- [ ] `grep` of the changes shows no f-string or `%` formatting inside any SQL statement
- [ ] `GET /login`, `/`, `/terms` and `/privacy` still render as before
