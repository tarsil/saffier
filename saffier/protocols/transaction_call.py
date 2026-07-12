from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from saffier.core.connection.database import Transaction


class TransactionCallProtocol(Protocol):
    @classmethod
    def __call__(cls, *, force_rollback: bool = False, **kwargs: Any) -> Transaction: ...


__all__ = ["TransactionCallProtocol"]
