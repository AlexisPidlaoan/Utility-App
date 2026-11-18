"""The two HTML pages (login and dashboard) and the dashboard's summary numbers."""
from flask import Blueprint, jsonify, redirect, render_template, session, url_for

from database import get_db
from helpers import current_user_id, login_required

bp = Blueprint("pages", __name__)

# Each query takes the user id as its only parameter.
STAT_QUERIES = {
    "links": "SELECT COUNT(*) FROM urls WHERE user_id = ?",
    "clicks": "SELECT COALESCE(SUM(clicks), 0) FROM urls WHERE user_id = ?",
    "records": "SELECT COUNT(*) FROM fake_records WHERE user_id = ?",
    "messages": "SELECT COUNT(*) FROM message_logs WHERE user_id = ?",
}


@bp.get("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("pages.index"))
    return render_template("login.html")


@bp.get("/")
@login_required
def index():
    return render_template("index.html", username=session.get("username", ""))


@bp.get("/api/stats")
@login_required
def stats():
    db, user_id = get_db(), current_user_id()
    return jsonify({name: db.execute(sql, (user_id,)).fetchone()[0]
                    for name, sql in STAT_QUERIES.items()})
