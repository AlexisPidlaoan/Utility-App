"""Small helpers shared by every route module."""
from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def json_body():
    """The request's JSON body as a dict (an empty dict if it is missing or not an object)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def api_error(message, status):
    """A JSON error response: {"error": message} with an HTTP status code."""
    return jsonify(error=message), status


def current_user_id():
    return session["user_id"]


def login_required(view):
    """Protect a route: API calls get a 401 error, page visits are sent to the login page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return api_error("Authentication required", 401)
            return redirect(url_for("pages.login_page"))
        return view(*args, **kwargs)
    return wrapped
