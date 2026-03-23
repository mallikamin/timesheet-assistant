"""Smoke tests — run before every deploy to catch template/route breakage."""

from starlette.testclient import TestClient

import app as myapp

client = TestClient(myapp.app)


def test_login_returns_html():
    r = client.get("/login")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_home_redirects_to_login():
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert "/login" in r.headers["location"]


def test_api_me_returns_json():
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["authenticated"] is False


if __name__ == "__main__":
    test_login_returns_html()
    test_home_redirects_to_login()
    test_api_me_returns_json()
    print("All smoke tests passed.")
