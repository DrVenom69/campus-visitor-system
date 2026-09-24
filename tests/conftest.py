import os

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from app import create_app, db
from tests.helpers import login, make_user


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """The default hash is deliberately slow; use a cheap one so the suite stays quick."""
    monkeypatch.setattr(
        "app.models.generate_password_hash",
        lambda password: generate_password_hash(password, method="pbkdf2:sha256:1000"),
    )


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": os.environ.get("TEST_DATABASE_URL", "sqlite://"),
        "SECRET_KEY": "test",
    })

    @app.teardown_request
    def forget_logged_in_user(error):
        # The fixture keeps one app context open for the whole test, so Flask would
        # otherwise reuse `g` and leak a login from one client into the next.
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        make_user("admin")
        make_user("host", email="host@campus.edu", name="Dr. Host")
        make_user("security")
        make_user("visitor")
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def as_role(app):
    """Return a client logged in as the given role: as_role('admin')."""

    def _as_role(role):
        client = app.test_client()
        email = "host@campus.edu" if role == "host" else f"{role}@campus.edu"
        assert login(client, email).status_code == 302
        return client

    return _as_role
