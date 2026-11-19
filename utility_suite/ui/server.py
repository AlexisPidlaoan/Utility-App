"""Background web server so short links still redirect and count clicks when opened in a browser."""
import threading

from werkzeug.serving import make_server

from app import create_app          # the Flask app in utility_suite/app.py

from .settings import HOST, PORT


def start_redirect_server():
    """Serve the Flask app in a daemon thread. Returns the server, or None if the port is busy."""
    flask_app = create_app()        # also creates the database tables on first run
    try:
        server = make_server(HOST, PORT, flask_app, threaded=True)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
