# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Spendly: a Flask expense tracker structured as a step-by-step teaching project. The landing, login, register, terms and privacy pages are implemented as static templates. Auth, the database and expense CRUD are still stubs, labelled "Step N" in the code.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # venv/ is gitignored
pip install -r requirements.txt                   # flask, werkzeug, pytest, pytest-flask
python app.py                                     # dev server, debug on, http://localhost:5001
pytest                                            # all tests (none exist yet)
pytest path/to/test_file.py::test_name            # a single test
```

There is no linter, formatter or build step.

## Architecture

- `app.py` is the whole backend: one `Flask` app with every route. Implemented routes only call `render_template`. The placeholder routes (`/logout`, `/profile`, `/expenses/add`, `/expenses/<int:id>/edit`, `/expenses/<int:id>/delete`) return a "coming in Step N" string; replace the stub body in place.
- Templates link with `url_for('<view function name>')`, so renaming a view function breaks them. Keep names such as `landing`, `login`, `register`, `terms` and `privacy`.
- `database/db.py` holds only a comment spec for Step 1. It should provide `get_db()` (SQLite with `row_factory` and foreign keys on), `init_db()` (`CREATE TABLE IF NOT EXISTS`) and `seed_db()`. The DB file `expense_tracker.db` is gitignored.
- `templates/base.html` is the shared layout (navbar, footer, Google Fonts). Pages extend it using the `title`, `head`, `content` and `scripts` blocks.
- `static/css/style.css` is the only stylesheet. Page-specific JS goes in the page's `{% block scripts %}`; the landing-page video modal is inline in `templates/landing.html`. `static/js/main.js` is an empty placeholder loaded on every page.

## Conventions

- Vanilla JS only, with no frameworks or libraries.
- Keep changes scoped to what is asked; prior requests explicitly said not to touch other parts of a page.
- `file.txt` is a scratch log of past prompts, not project code.
