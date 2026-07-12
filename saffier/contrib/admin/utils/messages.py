from __future__ import annotations

from contextvars import ContextVar
from typing import cast

try:
    from lilya.context import session as _session
except ImportError:  # pragma: no cover
    _session = None

_messages_var: ContextVar[list[dict[str, str]] | None] = ContextVar(
    "_admin_messages",
    default=None,
)


def _get_session_messages() -> list[dict[str, str]] | None:
    """Return the active Lilya session message list when one exists.

    The admin app installs Lilya session-context middleware, which makes flash
    messages survive redirects inside a single operator workflow. Direct service
    tests may run without that context, so the helper returns ``None`` instead
    of treating an absent session as an error.

    Returns:
        list[dict[str, str]] | None: Mutable session-backed message list, or
        ``None`` when no Lilya session context is available.
    """
    if _session is None:
        return None
    try:
        if not hasattr(_session, "messages"):
            _session.messages = []
        return cast("list[dict[str, str]]", _session.messages)
    except (LookupError, RuntimeError):
        return None


def add_message(level: str, message: str) -> None:
    """Add an admin flash message for the current request workflow.

    Messages are stored in Lilya's session context when a request is active so
    create, update, and delete redirects can display feedback on the next page.
    Outside a request, a context variable is used to preserve the same behavior
    for direct service tests.

    Args:
        level: Styling level such as ``"success"``, ``"info"``, ``"warning"``,
            or ``"error"``.
        message: Human-readable message displayed by the admin base template.
    """
    session_messages = _get_session_messages()
    if session_messages is not None:
        session_messages.append({"level": level, "text": message})
        return

    messages = list(_messages_var.get() or ())
    messages.append({"level": level, "text": message})
    _messages_var.set(messages)


def get_messages(peek: bool = False) -> list[dict[str, str]]:
    """Return pending admin flash messages.

    By default, messages are consumed after being read so they behave like
    standard flash messages. Passing ``peek=True`` is useful for diagnostics or
    tests that need to inspect the queue without clearing it.

    Args:
        peek: Whether to leave the underlying message queue untouched.

    Returns:
        list[dict[str, str]]: Message dictionaries with ``level`` and ``text``
        keys.
    """
    session_messages = _get_session_messages()
    if session_messages is not None:
        messages = list(session_messages)
        if not peek:
            session_messages.clear()
        return messages

    messages = list(_messages_var.get() or ())
    if not peek:
        _messages_var.set([])
    return messages


__all__ = ["add_message", "get_messages"]
