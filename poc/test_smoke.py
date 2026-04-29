"""Smoke tests — run before every deploy to catch template/route breakage.

Uses httpx.AsyncClient + ASGITransport directly (works across httpx 0.28+).
The CI workflow at .github/workflows/ci.yml runs an inline equivalent of
these checks too — keeping both in sync as a deliberate belt-and-braces.
"""

import asyncio

import httpx

import app as myapp


def _run(coro):
    return asyncio.run(coro)


async def _client():
    transport = httpx.ASGITransport(app=myapp.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _login_check():
    async with await _client() as c:
        r = await c.get("/login")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


async def _home_redirect_check():
    async with await _client() as c:
        r = await c.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert "/login" in r.headers["location"]


async def _api_me_check():
    async with await _client() as c:
        r = await c.get("/api/me")
        assert r.status_code == 200
        assert r.json()["authenticated"] is False


async def _health_check():
    async with await _client() as c:
        r = await c.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["model"].startswith("claude-")


def test_login_returns_html():
    _run(_login_check())


def test_home_redirects_to_login():
    _run(_home_redirect_check())


def test_api_me_returns_json():
    _run(_api_me_check())


def test_health_endpoint():
    _run(_health_check())


if __name__ == "__main__":
    _run(_login_check())
    _run(_home_redirect_check())
    _run(_api_me_check())
    _run(_health_check())
    print("All smoke tests passed.")
