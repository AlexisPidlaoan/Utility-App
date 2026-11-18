"""Settings for the Utility Suite, kept in one place."""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SETTINGS = {
    "DATABASE": os.environ.get("DATABASE", os.path.join(BASE_DIR, "utility_suite.db")),
    "SECRET_KEY": os.environ.get("SECRET_KEY"),     # None -> load_secret_key() fills it in
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "MAX_CONTENT_LENGTH": 1024 * 1024,              # reject request bodies over 1 MB
}


def load_secret_key():
    """Read the session key saved next to the app, or create it on first run.

    The key is stored in a file so logins survive Flask's debug reloader.
    Do not commit `.secret_key` to Git.
    """
    path = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()

    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # owner-only file
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return key
