"""Every module in this package is one Flask blueprint, one part of the app."""
from . import auth, fake_data, messaging, pages, shortener


def register_blueprints(app):
    for module in (auth, pages, fake_data, messaging, shortener):
        app.register_blueprint(module.bp)
