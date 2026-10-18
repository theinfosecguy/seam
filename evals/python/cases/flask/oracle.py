"""Check permanent-session cache headers with Flask test clients."""

from flask import Flask, session


def make_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "evaluation-only-public-key"
    app.config["TESTING"] = True

    @app.route("/seed")
    def seed():
        session["user"] = "alice"
        session.permanent = True
        return "seeded"

    @app.route("/public")
    def public():
        return "public content"

    @app.route("/read")
    def read():
        return session.get("user", "anonymous")

    return app


def test_security_regression() -> None:
    client = make_app().test_client()
    client.get("/seed")
    response = client.get("/public")
    assert "session=" in response.headers.get("Set-Cookie", "")
    assert "Cookie" in response.vary, (
        "EXPECTED_SECURITY_REGRESSION: refreshed cookie lacks Vary"
    )


def test_ordinary_request() -> None:
    response = make_app().test_client().get("/public")
    assert response.data == b"public content"
    assert "Set-Cookie" not in response.headers


def test_session_read() -> None:
    client = make_app().test_client()
    client.get("/seed")
    response = client.get("/read")
    assert response.data == b"alice"
    assert "Cookie" in response.vary


def test_refresh_disabled() -> None:
    app = make_app()
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False
    client = app.test_client()
    client.get("/seed")
    response = client.get("/public")
    assert response.data == b"public content"
    assert "Set-Cookie" not in response.headers
