"""Registration, login and logout. Password hashing itself lives in security.py."""
import re
import sqlite3

from flask import Blueprint, jsonify, session

from database import get_db
from helpers import api_error, json_body
from security import DUMMY_HASH, hash_password, verify_password

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def _read_credentials():
    data = json_body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    return username, password


def _sign_in(user_id, username):
    """Start a fresh session. Clearing the old one first prevents session fixation."""
    session.clear()
    session["user_id"] = user_id
    session["username"] = username


@bp.post("/api/register")
def register():
    username, password = _read_credentials()
    if not USERNAME_RE.fullmatch(username):
        return api_error("Username must be 3-30 characters: letters, numbers, underscore", 400)
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        return api_error(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters", 400)

    db = get_db()
    try:
        cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, hash_password(password)))
        db.commit()
    except sqlite3.IntegrityError:
        return api_error("Username is already taken", 409)

    _sign_in(cur.lastrowid, username)
    return jsonify(success=True, username=username), 201


@bp.post("/api/login")
def login():
    username, password = _read_credentials()
    user = get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)).fetchone()

    stored_hash = user["password_hash"] if user else DUMMY_HASH
    password_ok = verify_password(password, stored_hash)
    if not (user and password_ok):
        return api_error("Invalid username or password", 401)

    _sign_in(user["id"], user["username"])
    return jsonify(success=True, username=user["username"])


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(success=True)
