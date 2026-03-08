from __future__ import annotations

from contextvars import ContextVar

_messages_var: ContextVar[list[dict[str, str]] | None] = ContextVar(
    "_admin_messages",
    default=None,
)


def add_message(level: str, message: str) -> None:
    messages = list(_messages_var.get() or ())
    messages.append({"level": level, "text": message})
    _messages_var.set(messages)


def get_messages(peek: bool = False) -> list[dict[str, str]]:
    messages = list(_messages_var.get() or ())
    if not peek:
        _messages_var.set([])
    return messages


__all__ = ["add_message", "get_messages"]
