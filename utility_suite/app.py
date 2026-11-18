"""Developer & Admin Utility Suite (Category 3B: Utilities)

This file only builds and starts the app. The real work lives in:

    config.py            settings and the session key
    database.py          SQLite connection and first-run setup
    security.py          password hashing (hashlib)
    helpers.py           login_required, JSON helpers
    routes/auth.py       register / login / logout
    routes/pages.py      login page, dashboard page, summary numbers
    routes/shortener.py  3B.1  URL shortener with click tracking
    routes/messaging.py  3B.2  simulated SMS dispatcher
    routes/fake_data.py  3B.3  fake data generator (11 fields, stored in SQLite)

Run:  python app.py   ->  http://127.0.0.1:5000
"""
from flask import Flask

import database
from config import DEFAULT_SETTINGS, load_secret_key
from routes import register_blueprints


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.update(DEFAULT_SETTINGS)
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = load_secret_key()

    database.init_app(app)
    register_blueprints(app)
    return app


if __name__ == "__main__":
    # Debug mode is for development only; it binds to localhost so the debugger is not exposed.
    create_app().run(host="127.0.0.1", port=5000, debug=True)
