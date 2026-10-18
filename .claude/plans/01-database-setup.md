# Plan 01 — Database Setup (Step 1)

## Context
`database/db.py` is a comment-only stub and `app.py` has no DB wiring. Spec `.claude/specs/database-setup.md` (untracked, lives in the main checkout only) defines the data-layer foundation every later step (auth, profile, expense CRUD) depends on. No new routes, no new packages, no new files.

An earlier attempt (commit f853474) was reverted at the user's request. It differed from the spec in these ways, which this plan corrects:
- demo password was `demo1234`, spec says `demo123`
- 6 expenses, spec says 8 with at least one per category (7 categories)
- hard-coded Oct 2026 dates, spec says dates across the *current month*
- `created_at` default was `CURRENT_TIMESTAMP`, spec says `datetime('now')`
- extra `CHECK (amount > 0)` and an index, which the spec does not ask for (drop them)
- `init_db()`/`seed_db()` were called bare, spec says inside `app.app_context()`; `get_db` was not imported

## Files to change
1. `database/db.py` — replace stub
2. `app.py` — imports + startup calls

## `database/db.py`
- Imports: `os`, `sqlite3`, `datetime.date`, `werkzeug.security.generate_password_hash`.
- `DB_PATH` = `expense_tracker.db` in project root (already gitignored, per CLAUDE.md).
- `CATEGORIES` constant: Food, Transport, Bills, Health, Entertainment, Shopping, Other (exact list from spec §10).
- `get_db()`: `sqlite3.connect(DB_PATH)`, `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`, return conn.
- `init_db()`: `executescript` with `CREATE TABLE IF NOT EXISTS` for:
  - `users`: id PK AUTOINCREMENT, name NOT NULL, email UNIQUE NOT NULL, password_hash NOT NULL, created_at TEXT DEFAULT (datetime('now'))
  - `expenses`: id PK AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), amount REAL NOT NULL, category TEXT NOT NULL, date TEXT NOT NULL, description TEXT, created_at TEXT DEFAULT (datetime('now'))
  - Close the connection in `finally`.
- `seed_db()`:
  - Return early if `SELECT 1 FROM users LIMIT 1` finds a row.
  - Insert Demo User / `demo@spendly.com` / `generate_password_hash("demo123")` with parameterized SQL; take `lastrowid`.
  - Insert 8 expenses via `executemany` with `?` placeholders: all 7 categories once, plus one extra (e.g. second Food). Amounts are floats. Dates built from today's year and month (`date.today().replace(day=d).isoformat()`) with d spread over 1–28, so they are always valid `YYYY-MM-DD` in the current month.
  - Commit; close in `finally`.
- No string formatting in SQL anywhere.

## `app.py`
- `from database.db import get_db, init_db, seed_db` (spec §6 lists `get_db` too, even though startup only needs the other two).
- After `app = Flask(__name__)`:
  ```python
  with app.app_context():
      init_db()
      seed_db()
  ```
- Leave all routes and the `port=5001` run line unchanged; stub routes stay stubs (CLAUDE.md).

## Branch / delivery
- Work on `feature/databse-setup` (current branch in worktree `.claude/worktrees/setup-database`; note the "databse" spelling as the user typed it).
- Copy this plan to `.claude/plans/01-database-setup.md` in the worktree (plan-mode restricted writing there).
- Commit with the Co-Authored-By trailer, push the branch, no merge to main.

## Verification
Run from the worktree, with `expense_tracker.db` deleted first:
1. `python -c "import app"` creates the DB file and exits cleanly (no errors).
2. Run it twice more: `SELECT COUNT(*)` stays at 1 user and 8 expenses (no duplicates).
3. `PRAGMA table_info` for both tables matches the spec columns, nullability and defaults.
4. Row check: all 7 categories appear, dates are all in the current month and match `YYYY-MM-DD`, amounts are REAL, and `check_password_hash(hash, "demo123")` is true.
5. Constraint checks: a duplicate email insert raises `IntegrityError` (UNIQUE), and an expense with `user_id=999` raises `IntegrityError` (FK).
6. `python app.py` starts on port 5001 and `GET /` returns 200 (via `curl`, then stop the server).
7. `grep` db.py for f-strings or `%` formatting near SQL: none.
8. Delete the test `expense_tracker.db` afterwards (it is gitignored, but keep the tree clean).
