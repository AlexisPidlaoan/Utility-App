"""3B.1  URL shortener: create short links, redirect visitors, and track clicks."""
import re
import secrets
import sqlite3
import string
from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, request

from database import get_db
from helpers import api_error, current_user_id, json_body, login_required

bp = Blueprint("shortener", __name__)

BASE62 = string.digits + string.ascii_letters
BASE62_OFFSET = 62 ** 5                 # keeps generated codes at least 6 characters long
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_CODES = {"api", "login", "logout", "register", "static", "admin", "dashboard"}
CODE_MODES = ("base62", "random")
MAX_RANDOM_ATTEMPTS = 10


# --------------------------------------------------------------------------
# Code generation and validation
# --------------------------------------------------------------------------
def base62_encode(number):
    if number == 0:
        return BASE62[0]
    chars = []
    while number:
        number, remainder = divmod(number, 62)
        chars.append(BASE62[remainder])
    return "".join(reversed(chars))


def random_code(length=6):
    return "".join(secrets.choice(BASE62) for _ in range(length))


def is_valid_url(value):
    """Only absolute http(s) URLs: blocks javascript:, data:, file: and similar."""
    if not value or len(value) > 2048 or any(c.isspace() for c in value):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_alias(alias):
    """Return an error message, or None if the alias is acceptable."""
    if not ALIAS_RE.fullmatch(alias):
        return "Alias must be 3-32 characters: letters, numbers, - or _"
    if alias.lower() in RESERVED_CODES:
        return "That alias is reserved"
    return None


# --------------------------------------------------------------------------
# Saving a link (one function per way of choosing the short code)
# --------------------------------------------------------------------------
def _insert_url(db, user_id, url, code):
    """Insert a link and return its row id, or None if `code` is already taken."""
    try:
        cur = db.execute(
            "INSERT INTO urls (user_id, original_url, short_code) VALUES (?, ?, ?)",
            (user_id, url, code))
    except sqlite3.IntegrityError:
        return None
    return cur.lastrowid


def _set_short_code(db, row_id, code):
    """Give an existing link a new code. Returns False if the code is already taken."""
    try:
        db.execute("UPDATE urls SET short_code = ? WHERE id = ?", (code, row_id))
    except sqlite3.IntegrityError:
        return False
    return True


def create_with_alias(db, user_id, url, alias):
    """Save the link under the user's own alias. Returns the code, or None if it is taken."""
    if _insert_url(db, user_id, url, alias) is None:
        return None
    db.commit()
    return alias


def create_with_random_code(db, user_id, url):
    """Try random codes until one is free. Returns the code, or None after too many clashes."""
    for _ in range(MAX_RANDOM_ATTEMPTS):
        code = random_code()
        if _insert_url(db, user_id, url, code) is not None:
            db.commit()
            return code
    return None


def create_with_base62_code(db, user_id, url):
    """Encode the row id in Base62. Row ids are unique, so the code is unique by construction."""
    row_id = _insert_url(db, user_id, url, "pending-" + secrets.token_hex(8))
    code = base62_encode(row_id + BASE62_OFFSET)
    while not _set_short_code(db, row_id, code):
        code = random_code(7)           # rare: a custom alias already uses this exact string
    db.commit()
    return code


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@bp.post("/api/shorten")
@login_required
def shorten():
    data = json_body()
    url = str(data.get("url") or "").strip()
    alias = str(data.get("custom_alias") or "").strip()
    mode = data.get("mode", "base62")

    if not is_valid_url(url):
        return api_error("Enter a valid http:// or https:// URL", 400)
    if mode not in CODE_MODES:
        return api_error("mode must be 'base62' or 'random'", 400)

    db, user_id = get_db(), current_user_id()

    if alias:
        problem = validate_alias(alias)
        if problem:
            return api_error(problem, 400)
        code = create_with_alias(db, user_id, url, alias)
        if code is None:
            return api_error("Custom alias already in use", 409)
    elif mode == "random":
        code = create_with_random_code(db, user_id, url)
        if code is None:
            return api_error("Could not generate a unique code, try again", 500)
    else:
        code = create_with_base62_code(db, user_id, url)

    return jsonify(short_code=code, short_url=request.host_url + code), 201


@bp.get("/api/urls")
@login_required
def list_urls():
    rows = get_db().execute(
        "SELECT original_url, short_code, created_at, clicks FROM urls "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 200", (current_user_id(),)).fetchall()
    return jsonify(urls=[dict(r, short_url=request.host_url + r["short_code"]) for r in rows])


@bp.get("/api/urls/<code>/stats")
@login_required
def url_stats(code):
    db = get_db()
    link = db.execute(
        "SELECT id, original_url, short_code, clicks, created_at FROM urls "
        "WHERE short_code = ? AND user_id = ?", (code, current_user_id())).fetchone()
    if not link:
        return api_error("Link not found", 404)

    by_day = db.execute(
        "SELECT date(clicked_at) AS day, COUNT(*) AS clicks FROM url_clicks "
        "WHERE url_id = ? GROUP BY day ORDER BY day DESC LIMIT 7", (link["id"],)).fetchall()
    recent = db.execute(
        "SELECT clicked_at, referrer, user_agent FROM url_clicks "
        "WHERE url_id = ? ORDER BY id DESC LIMIT 10", (link["id"],)).fetchall()
    return jsonify(short_code=link["short_code"], original_url=link["original_url"],
                   total_clicks=link["clicks"], created_at=link["created_at"],
                   by_day=[dict(r) for r in by_day], recent=[dict(r) for r in recent])


@bp.delete("/api/urls/<code>")
@login_required
def delete_url(code):
    db = get_db()
    cur = db.execute("DELETE FROM urls WHERE short_code = ? AND user_id = ?",
                     (code, current_user_id()))
    db.commit()
    if cur.rowcount == 0:
        return api_error("Link not found", 404)
    return jsonify(success=True)


@bp.get("/<short_code>")
def follow_short_url(short_code):
    """Public: anyone with the short link is redirected. Each visit is counted and logged."""
    db = get_db()
    link = db.execute("SELECT id, original_url FROM urls WHERE short_code = ?",
                      (short_code,)).fetchone()
    if not link:
        return api_error("Short URL not found", 404)

    db.execute("UPDATE urls SET clicks = clicks + 1 WHERE id = ?", (link["id"],))
    db.execute("INSERT INTO url_clicks (url_id, referrer, user_agent) VALUES (?, ?, ?)",
               (link["id"], (request.referrer or "")[:500], request.user_agent.string[:300]))
    db.commit()
    return redirect(link["original_url"], code=302)     # 302 so every click reaches us
