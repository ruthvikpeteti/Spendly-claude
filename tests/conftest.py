import pytest

from database import db

# app.py runs init_db()/seed_db() on import, so point the DB at a throwaway
# file first; the real expense_tracker.db must never be touched by tests.
import tempfile
import os

_import_dir = tempfile.mkdtemp()
db.DB_PATH = os.path.join(_import_dir, "import.db")

from app import app as flask_app  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A new SQLite file with the schema and the seeded demo user."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    return db.DB_PATH


@pytest.fixture
def client(fresh_db):
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


@pytest.fixture
def demo_user_id(fresh_db):
    return db.get_user_by_email("demo@spendly.com")["id"]


@pytest.fixture
def empty_user_id(fresh_db):
    """A registered user with no expenses."""
    return db.create_user("Empty User", "empty@example.com", "password123")


def login(client, user_id, name):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name
