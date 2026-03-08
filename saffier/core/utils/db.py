from __future__ import annotations

import warnings
from base64 import b32encode
from collections.abc import Iterable
from contextvars import ContextVar
from functools import lru_cache
from hashlib import blake2b
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from saffier.core.connection.database import Database


CHECK_DB_CONNECTION_SILENCED = ContextVar("CHECK_DB_CONNECTION_SILENCED", default=False)
FORCE_FIELDS_NULLABLE = ContextVar(
    "FORCE_FIELDS_NULLABLE",
    default=(),
)


def check_db_connection(db: Database, stacklevel: int = 3) -> None:
    """
    Mirror Edgy's warning/error contract for disconnected databases.
    """
    from saffier.exceptions import DatabaseNotConnectedWarning

    if getattr(db, "is_connected", False):
        return

    if getattr(db, "force_rollback", False):
        raise RuntimeError("db is not connected.")

    if not CHECK_DB_CONNECTION_SILENCED.get():
        warnings.warn(
            "Database not connected. Executing operation is inperformant.",
            DatabaseNotConnectedWarning,
            stacklevel=stacklevel,
        )


def _hash_to_identifier(key: str | bytes) -> str:
    if isinstance(key, str):
        key = key.encode()
    return f"_{b32encode(blake2b(key, digest_size=16).digest()).decode().rstrip('=')}"


@lru_cache(512, typed=False)
def _hash_tablekey(tablekey: str, prefix: str) -> str:
    return f"_join{_hash_to_identifier(f'{tablekey}_{prefix}')}"


def hash_tablekey(*, tablekey: str, prefix: str) -> str:
    if not prefix:
        return tablekey
    return _hash_tablekey(tablekey, prefix)


def hash_names(
    field_or_col_names: Iterable[str], *, inner_prefix: str, outer_prefix: str = ""
) -> str:
    hashed = _hash_to_identifier(f"{inner_prefix}_{','.join(sorted(field_or_col_names))}")
    if outer_prefix:
        return f"{outer_prefix}{hashed}"
    return hashed


def force_fields_nullable_as_list_string(apostroph: str = '"') -> str:
    items = FORCE_FIELDS_NULLABLE.get()
    if not all(apostroph not in item[0] and apostroph not in item[1] for item in items):
        raise RuntimeError(f"{apostroph} was found in items")
    joined = ", ".join(
        f"({apostroph}{item[0]}{apostroph}, {apostroph}{item[1]}{apostroph})" for item in items
    )
    return f"[{joined}]"


__all__ = [
    "CHECK_DB_CONNECTION_SILENCED",
    "FORCE_FIELDS_NULLABLE",
    "check_db_connection",
    "force_fields_nullable_as_list_string",
    "hash_names",
    "hash_tablekey",
]
