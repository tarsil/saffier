import base64

import pytest

from saffier.contrib.admin.permissions import BasicAuthMiddleware


@pytest.mark.anyio
async def test_basic_auth_middleware_allows_and_denies():
    calls = {"passed": False}

    async def app(scope, receive, send):
        calls["passed"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BasicAuthMiddleware(app, username="admin", password="secret")

    messages = []

    async def send(message):
        messages.append(message)

    await middleware({"type": "http", "headers": []}, None, send)
    assert messages[0]["status"] == 401
    assert calls["passed"] is False

    messages.clear()
    wrong = [(b"authorization", b"Basic badtoken")]
    await middleware({"type": "http", "headers": wrong}, None, send)
    assert messages[0]["status"] == 401
    assert calls["passed"] is False

    messages.clear()
    token = base64.b64encode(b"admin:secret")
    ok = [(b"authorization", b"Basic " + token)]
    await middleware({"type": "http", "headers": ok}, None, send)
    assert calls["passed"] is True
    assert messages[0]["status"] == 200
