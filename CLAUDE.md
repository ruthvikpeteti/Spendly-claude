# CLAUDE.md
Spendly is a lightweight personal expense tracker built with Flask and SQLite.
---
## Architecture
```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   └── db.py           # SQLite helpers: get_db(), init_db(), seed_db()
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── landing.css     # Landing-page-only styles
│   └── js/
│       └── main.js         # Vanilla JS only
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine


## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /register` | Implemented — renders `register.html` |
| `GET/POST /login` | Implemented — renders `login.html`, verifies credentials, sets session |
| `GET /logout` | Implemented — clears session, redirects to `/` |
| `GET /profile` | Implemented — renders `profile.html` with the logged-in user's real data from `database/queries.py`; redirects to `/login` when logged out |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<id>/edit` | Stub — Step 8 |
| `GET /expenses/<id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py` (schema, users, seeding) or `database/queries.py` (read-only profile queries)
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The app runs on **port 5001**, not the Flask default 5000 — don't change this


This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Spendly: a Flask expense tracker structured as a step-by-step teaching project. The landing, login, register, terms, privacy and profile pages are implemented, and login/logout use Flask's cookie session. The profile page shows the logged-in user's real data (Step 5). Expense CRUD is still stubs, labelled "Step N" in the code.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # venv/ is gitignored
pip install -r requirements.txt                   # flask, werkzeug, pytest, pytest-flask
python app.py                                     # dev server, debug on, http://localhost:5001
pytest                                            # all tests (tests/ uses a throwaway temp DB)
pytest path/to/test_file.py::test_name            # a single test
```

There is no linter, formatter or build step.

## Architecture

- `app.py` is the whole backend: one `Flask` app with every route. Implemented routes only call `render_template`. The placeholder routes (`/expenses/add`, `/expenses/<int:id>/edit`, `/expenses/<int:id>/delete`) return a "coming in Step N" string; replace the stub body in place.
- Templates link with `url_for('<view function name>')`, so renaming a view function breaks them. Keep names such as `landing`, `login`, `register`, `terms` and `privacy`.
- `database/db.py` provides `get_db()` (SQLite with `row_factory` and foreign keys on), `init_db()` (`CREATE TABLE IF NOT EXISTS`), `seed_db()`, `get_user_by_email()` and `create_user()`. The DB file `expense_tracker.db` is gitignored.
- `database/queries.py` holds the read-only profile queries (`get_user_by_id`, `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`). No Flask imports; each opens and closes its own connection.
- `templates/base.html` is the shared layout (navbar, footer, Google Fonts). Pages extend it using the `title`, `head`, `content` and `scripts` blocks.
- `static/css/style.css` is the only stylesheet. Page-specific JS goes in the page's `{% block scripts %}`; the landing-page video modal is inline in `templates/landing.html`. `static/js/main.js` is an empty placeholder loaded on every page.

## Conventions

- Vanilla JS only, with no frameworks or libraries.
- Keep changes scoped to what is asked; prior requests explicitly said not to touch other parts of a page.
- `file.txt` is a scratch log of past prompts, not project code.
