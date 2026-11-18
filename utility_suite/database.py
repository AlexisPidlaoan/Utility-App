"""SQLite connection handling and first-run setup."""
import os
import sqlite3
from datetime import datetime

from flask import current_app, g

from config import BASE_DIR

SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")


def get_db():
    """Return this request's connection. It is opened on first use and closed automatically."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _move_legacy_database(path):
    """Set aside a database made by the first starter version (renamed, never deleted).

    That version used the same file name, but its `urls` table has no user_id column.
    CREATE TABLE IF NOT EXISTS would keep the old table and the app would crash.
    """
    if not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(urls)")]
    finally:
        conn.close()

    if columns and "user_id" not in columns:
        backup = f"{path}.legacy-{datetime.now():%Y%m%d-%H%M%S}"
        os.replace(path, backup)
        print(f"[init_db] Old-format database moved to {backup}; starting with a fresh one.")


def init_db(path):
    """Create the tables from schema.sql if they do not exist yet."""
    _move_legacy_database(path)
    conn = sqlite3.connect(path)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def init_app(app):
    """Hook the database into a Flask app: close connections after each request, create tables."""
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE"])
