"""SQLite connection for the GUI. It uses the same database file as the web version."""
import sqlite3

from config import DEFAULT_SETTINGS


def connect():
    """One long-lived connection for the whole window (Tkinter runs on a single thread).

    Because it stays open, any failed insert must be followed by db.rollback(); otherwise the
    open transaction keeps the database locked for the background redirect server.
    """
    conn = sqlite3.connect(DEFAULT_SETTINGS["DATABASE"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
