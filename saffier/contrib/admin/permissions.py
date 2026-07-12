from __future__ import annotations

import base64
import secrets
from typing import Any

from lilya.exceptions import PermissionDenied
from lilya.protocols.permissions import PermissionProtocol
from lilya.requests import Request
from lilya.types import ASGIApp, Receive, Scope, Send


def _encode_basic_credentials(username: str, password: str) -> str:
    """Build the canonical HTTP Basic credential payload.

    HTTP Basic authentication compares the base64-encoded ``username:password``
    value after the ``Basic`` scheme. Centralizing the encoding keeps the
    middleware and Lilya permission class byte-for-byte consistent, and avoids
    recomputing the expected value for every request.

    Args:
        username: Expected administrator username.
        password: Expected administrator password.

    Returns:
        str: Base64-encoded credential payload without the ``Basic`` scheme.
    """
    return base64.b64encode(f"{username}:{password}".encode()).decode()


def _is_authorized_basic_header(auth: str | None, expected_credentials: str) -> bool:
    """Validate an incoming HTTP Basic authorization header.

    The helper accepts the raw ``Authorization`` header value and returns a
    boolean rather than raising so both public admin auth surfaces can choose
    their own denial behavior: the middleware emits an ASGI response, while the
    permission-protocol class raises Lilya's ``PermissionDenied`` exception.

    Args:
        auth: Raw ``Authorization`` header value, if present.
        expected_credentials: Encoded credential payload created by
            ``_encode_basic_credentials``.

    Returns:
        bool: ``True`` when the header uses the Basic scheme and the supplied
        credential payload matches in constant time.
    """
    if not auth:
        return False

    try:
        scheme, credentials = auth.split(" ", 1)
    except ValueError:
        return False

    return scheme.lower() == "basic" and secrets.compare_digest(
        credentials,
        expected_credentials,
    )


def _challenge_headers(realm: str) -> dict[str, str]:
    """Return the standard Basic-auth challenge headers.

    Args:
        realm: Browser-visible authentication realm shown in the credentials
            prompt.

    Returns:
        dict[str, str]: Headers suitable for Lilya exceptions or ASGI response
        messages.
    """
    return {"WWW-Authenticate": f'Basic realm="{realm}", charset="UTF-8"'}


class BasicAuthAccess(PermissionProtocol):
    """Lilya permission-protocol implementation for Saffier admin Basic auth.

    ``BasicAuthMiddleware`` is the default protection used by
    ``create_admin_app()`` because it can be inserted directly into the Lilya
    middleware stack. ``BasicAuthAccess`` exposes the same credential check as a
    Lilya permission protocol for applications that build their own admin routes
    or permission stacks and want authentication failures to use Lilya's native
    ``PermissionDenied`` flow.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        username: str = "admin",
        password: str,
        print_pw: bool = False,
        realm: str = "Saffier Admin",
    ) -> None:
        """Store the downstream app and expected Basic auth credentials.

        Args:
            app: Downstream ASGI application to call after successful
                authentication.
            username: Expected Basic auth username.
            password: Expected Basic auth password.
            print_pw: Whether to print the configured password during
                initialization for local development workflows.
            realm: Browser-visible Basic auth realm included in challenge
                responses.
        """
        self.app = app
        self.basic_string = _encode_basic_credentials(username, password)
        self.realm = realm
        if print_pw:
            print("The admin panel password is:", password)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Authorize one Lilya permission-protected ASGI request.

        Non-HTTP scopes are passed through unchanged. HTTP requests must provide
        valid Basic credentials; invalid or missing credentials raise Lilya's
        ``PermissionDenied`` with a standard browser challenge header.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Raises:
            PermissionDenied: If the request is HTTP and does not contain valid
            Basic auth credentials.
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope, receive=receive, send=send)
        if not _is_authorized_basic_header(
            request.headers.get("Authorization"),
            self.basic_string,
        ):
            raise PermissionDenied(status_code=401, headers=_challenge_headers(self.realm))

        await self.app(scope, receive, send)


class BasicAuthMiddleware:
    """ASGI middleware implementing HTTP Basic auth for the admin app.

    The middleware protects only HTTP requests and returns a standard ``401``
    challenge when credentials are missing or invalid. It shares the exact
    credential parser with ``BasicAuthAccess`` so the middleware and
    permission-protocol surfaces behave consistently.
    """

    def __init__(self, app: Any, *, username: str = "admin", password: str) -> None:
        """Store the downstream app and expected Basic auth credentials.

        Credentials are encoded once during middleware construction so each
        request only needs a constant-time comparison against the incoming
        header value.

        Args:
            app: Downstream ASGI application.
            username: Expected Basic auth username.
            password: Expected Basic auth password.
        """
        self.app = app
        self.basic_string = _encode_basic_credentials(username, password)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Authorize one ASGI request before dispatching downstream.

        Non-HTTP scopes are passed through unchanged. HTTP requests must provide
        a Basic authorization header whose credentials match the configured
        values, otherwise the middleware emits a challenge response.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }

        if not _is_authorized_basic_header(headers.get("authorization"), self.basic_string):
            await self._deny(send)
            return

        await self.app(scope, receive, send)

    async def _deny(self, send: Any) -> None:
        """Emit the Basic auth challenge response.

        Args:
            send: ASGI send callable receiving the response start and body
                messages.
        """
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (
                        b"www-authenticate",
                        _challenge_headers("Saffier Admin")["WWW-Authenticate"].encode(),
                    ),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"Unauthorized"})


__all__ = [
    "BasicAuthAccess",
    "BasicAuthMiddleware",
    "PermissionDenied",
    "PermissionProtocol",
]
