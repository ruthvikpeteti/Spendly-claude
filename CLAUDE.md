# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Spendly" — a Flask expense tracker built as a step-by-step teaching project. Only the landing, login/register, terms and privacy pages are real; the rest is scaffolding to be filled in by numbered "Steps".

## Commands

```bash
python -m venv venv && source venv/bin/activate   # venv/ is gitignored
pip install -r requirements.txt                   # flask, werkzeug, pytest, pytest-flask
python app.py                                     # dev server on http://localhost:5001 (debug on)
pytest                                            # no tests exist yet; pytest-flask is installed
pytest path/to/test_file.py::test_name            # run a single test
```

No linter or build step is configured.

## Architecture

- `app.py` — single Flask app; all routes live here. Real routes just `render_template`. Placeholder routes (`/logout`, `/profile`, `/expenses/add`, `/expenses/<int:id>/edit|delete`) return stub strings labelled with their Step number (3, 4, 7, 8, 9) — replace the stub rather than adding a parallel route. Templates link via `url_for('<view function name>')` (`landing`, `login`, `register`, `terms`, `privacy`), so renaming a view function breaks those links.
- `database/db.py` — currently only a comment spec (Step 1). It is meant to provide `get_db()` (SQLite connection with `row_factory` and foreign keys enabled), `init_db()` (`CREATE TABLE IF NOT EXISTS`), and `seed_db()`. The SQLite file `expense_tracker.db` is gitignored.
- `templates/base.html` — shared layout (navbar, footer, Google Fonts); pages extend it via `{% block title %}`, `{% block head %}`, `{% block content %}`. Use `url_for(...)` for links and static assets.
- `static/css/style.css` is the single stylesheet. `static/js/main.js` is essentially empty; the landing-page modal script is inline in `templates/landing.html`.

## Conventions

- Vanilla JS only — no frameworks or JS libraries (e.g. the landing-page video modal is plain JS).
- Past tasks were scoped narrowly ("do not modify any other part of the page"); keep changes limited to what is asked. `file.txt` is the user's scratch log of prompts, not project code.
