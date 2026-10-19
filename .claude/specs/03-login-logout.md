# Spec: Login and Logout

## Overview

Make sign-in and sign-out work. Today `GET /login` only renders a static form whose `POST` has nowhere to go, and `GET /logout` is a stub that returns a string. This step adds the `POST /login` handler, which checks the submitted email and password against the `users` table and, on success, records the user in a Flask session. It also implements `/logout` to clear that session. Registration (Step 2) creates accounts but deliberately does not log anyone in, so this is the step that introduces authentication state. Every logged-in page that follows (profile, add/edit/delete expense) depends on it.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`, seeded demo user)
- Step 2 — Registration (`create_user()`, `get_user_by_email()`, password hashing with werkzeug)

## Routes

- `GET /login` — render the empty login form (already implemented). If the visitor is already logged in, redirect to `/` instead — public
- `POST /login` — validate credentials; on success store the user in the session and redirect to `/`; on failure re-render the form with an error message — public
- `GET /logout` — clear the session and redirect to `/` — logged-in (a logged-out visitor is also redirected to `/`, no error)

Implement both methods on the existing `login` view function (`methods=["GET", "POST"]`). Replace the body of the existing `logout` stub in place. Do not rename either function; templates link to them via `url_for('login')` and `url_for('logout')`.

Post-login destination is the landing page (`url_for('landing')`) because `/profile` is still a Step 4 stub. Step 4 can repoint the redirect.

## Database changes

No database changes. The `users` table already has `id`, `name`, `email` (UNIQUE) and `password_hash`.

No new DB helpers. `get_user_by_email()` from Step 2 already returns the full row, including `password_hash`. Verify the password in the route with `check_password_hash` from `werkzeug.security`; this is not DB logic.

## Templates

- **Create:** none
- **Modify:** `templates/login.html`
  - Change the hardcoded `action="/login"` to `action="{{ url_for('login') }}"`
  - Re-populate the email input after a failed submit (`value="{{ email or '' }}"`); never re-populate the password
  - Keep the existing `.auth-error` block for the `error` string
- **Modify:** `templates/base.html`
  - In `.nav-links`, branch on `session.get('user_id')`:
    - logged out: keep the existing "Sign in" and "Get started" links
    - logged in: show "Sign out" linking to `{{ url_for('logout') }}` (reuse the existing nav link styling; no "Get started" CTA)

## Files to change

- `app.py` — import `session`, `check_password_hash`; set `app.secret_key`; extend `login` to handle `POST`; implement `logout`
- `templates/login.html` — `url_for` action and email re-population
- `templates/base.html` — logged-in/logged-out nav links
- `CLAUDE.md` — update the "Implemented vs stub routes" table: `GET /login` implemented (POST), `GET /logout` implemented

## Files to create

None.

## New dependencies

No new dependencies. Flask's built-in cookie session and `werkzeug.security` are already available.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings or `%` formatting in SQL
- Passwords hashed with werkzeug; verify with `check_password_hash`; never log or echo the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic stays in `database/db.py`; the route reads the form, calls `get_user_by_email()`, checks the hash, sets the session, and renders or redirects
- Use Flask's built-in `session` (signed cookie). No Flask-Login, no new packages
- Set `app.secret_key` from the `SECRET_KEY` environment variable with a clearly-labelled development fallback string. Do not generate a random key at startup (it would invalidate sessions on every debug reload)
- Store only `user_id` and `user_name` in the session — never the password hash or the whole row
- Call `session.clear()` before setting the user on successful login, to avoid carrying over stale session data
- Normalise the email the same way registration does: strip and lower-case before lookup
- Use one generic error for both an unknown email and a wrong password: "Invalid email or password." Do not reveal which one was wrong
- Empty email or password → re-render with "Email and password are required."
- Never use a bare `return "string"` — render a template or redirect
- Use `url_for()` for every internal link and redirect — no hardcoded URLs
- Do not implement `/profile`, `/expenses/*` or any route protection or login-required decorator beyond what logout needs. Those belong to later steps
- Do not touch the other stub routes (`/profile`, `/expenses/*`)
- Do not change the registration flow (it still redirects to `/login` and does not log the user in)
- Do not change the port (5001)

## Definition of done

- [ ] `python app.py` starts on port 5001 without errors
- [ ] `GET /login` renders the form and the form's `action` resolves to `/login` via `url_for`
- [ ] Logging in as `demo@spendly.com` / `demo123` redirects to `/` and the navbar then shows "Sign out" instead of "Sign in" / "Get started"
- [ ] The email is matched case-insensitively and ignores surrounding whitespace (`  Demo@Spendly.com ` works)
- [ ] A wrong password for an existing email shows "Invalid email or password." and does not log in
- [ ] An unknown email shows the same "Invalid email or password." message
- [ ] Submitting with an empty email or password (bypassing the `required` attribute) shows "Email and password are required."
- [ ] After a failed login the email field keeps its value and the password field is empty
- [ ] A user registered via `/register` can then log in with the same credentials
- [ ] After login the browser holds a signed `session` cookie; it contains no password or hash in plain form
- [ ] Visiting `/login` while logged in redirects to `/`
- [ ] `GET /logout` redirects to `/`, the navbar returns to "Sign in" / "Get started", and the session cookie no longer identifies the user
- [ ] Visiting `/logout` while logged out redirects to `/` without an error
- [ ] The session survives a dev-server auto-reload (the secret key is stable)
- [ ] `GET /`, `/register`, `/terms` and `/privacy` still render as before
- [ ] `grep` of the changes shows no f-string or `%` formatting inside any SQL statement
- [ ] No new entries in `requirements.txt`
