import base64

import pytest

from saffier.contrib.admin.permissions import (
    BasicAuthAccess,
    BasicAuthMiddleware,
    PermissionDenied,
)


@pytest.mark.anyio
async def test_basic_auth_middleware_allows_and_denies():
    """Verify middleware Basic auth emits ASGI responses for app mounting.

    The admin application installs ``BasicAuthMiddleware`` in the Lilya
    middleware stack. This test exercises missing, invalid, and valid
    credentials through the real ASGI callable and confirms unauthorized
    requests do not reach the downstream app.
    """
    calls = {"passed": False}

    async def app(scope, receive, send):
        """Record that the downstream app was reached.

        Args:
            scope: ASGI scope passed by the middleware.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        calls["passed"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BasicAuthMiddleware(app, username="admin", password="secret")

    messages = []

    async def send(message):
        """Collect ASGI response messages emitted by the middleware.

        Args:
            message: ASGI response message.
        """
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


@pytest.mark.anyio
async def test_basic_auth_access_uses_lilya_permission_denials() -> None:
    """Verify permission-protocol Basic auth raises Lilya denials.

    Applications that wire the admin through Lilya permission stacks need an
    exception-based permission class instead of response-emitting middleware.
    This test proves missing or invalid credentials raise ``PermissionDenied``
    with a Basic-auth challenge, while valid credentials dispatch downstream.
    """
    calls = {"passed": False}

    async def app(scope, receive, send):
        """Record successful permission dispatch.

        Args:
            scope: ASGI scope passed by the permission class.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        calls["passed"] = True

    access = BasicAuthAccess(app, username="admin", password="secret")

    with pytest.raises(PermissionDenied) as missing:
        await access({"type": "http", "headers": []}, None, None)
    assert missing.value.status_code == 401
    assert missing.value.headers["WWW-Authenticate"].startswith("Basic realm=")

    wrong = [(b"authorization", b"Bearer token")]
    with pytest.raises(PermissionDenied):
        await access({"type": "http", "headers": wrong}, None, None)

    token = base64.b64encode(b"admin:secret")
    ok = [(b"authorization", b"Basic " + token)]
    await access({"type": "http", "headers": ok}, None, None)

    assert calls["passed"] is True
