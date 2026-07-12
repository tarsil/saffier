from __future__ import annotations

import warnings
from base64 import b32encode
from collections.abc import Generator, Iterable
from contextlib import contextmanager
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
    Enforce Saffier's warning/error contract for disconnected databases.

    Normal disconnected operations emit a warning so legacy startup patterns can
    still be diagnosed without failing immediately. Forced rollback contexts are
    stricter because they require an active connection to guarantee rollback
    semantics.
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


def _process_force_field_nullable(item: str | tuple[str, str]) -> tuple[str, str]:
    """Normalize one forced-nullable field selector.

    Migration commands accept selectors in the user-facing ``Model:field``
    format because that is practical to type on the command line. Migration
    templates and the registry helper use a normalized ``(model_name,
    field_name)`` tuple instead, where an empty model name means "every model
    with this field". This helper performs that conversion once and gives
    callers a clear validation error before Alembic starts autogeneration.

    Args:
        item: Either a ``Model:field`` string, a ``:field`` wildcard string, or
            an already normalized ``(model_name, field_name)`` tuple.

    Returns:
        tuple[str, str]: Normalized model and field selector.

    Raises:
        ValueError: If the selector cannot unambiguously describe exactly one
            model/field pair.
    """
    if isinstance(item, tuple):
        result = item
    else:
        if item.count(":") != 1:
            raise ValueError('Forced nullable fields must use "model:field" or ":field" syntax.')
        result = tuple(item.split(":", 1))

    if (
        not isinstance(result, tuple)
        or len(result) != 2
        or not isinstance(result[0], str)
        or not isinstance(result[1], str)
        or not result[1]
    ):
        raise ValueError(
            'Forced nullable fields must resolve to a "(model_name, field_name)" tuple.'
        )
    return result


@contextmanager
def with_force_fields_nullable(
    inp: Iterable[str | tuple[str, str]] | None,
) -> Generator[None, None, None]:
    """Temporarily mark selected model fields as nullable.

    This context is used by migration generation, where an existing table may
    need a new required column added safely. While the context is active,
    Saffier's model metadata reports selected fields as nullable so Alembic can
    emit DDL that works against rows that already exist. The generated migration
    then records the selectors and asks the registry to backfill defaults after
    the migration runs online.

    Args:
        inp: Iterable of ``Model:field`` strings, ``:field`` wildcard strings,
            or normalized ``(model_name, field_name)`` tuples. ``None`` is
            treated like an empty iterable so command callers can pass through
            optional option values directly.

    Yields:
        None: Control while the forced-nullable selectors are active.
    """
    token = FORCE_FIELDS_NULLABLE.set(
        tuple(_process_force_field_nullable(item) for item in inp or ())
    )
    try:
        yield
    finally:
        FORCE_FIELDS_NULLABLE.reset(token)


def force_fields_nullable_as_list_string(apostroph: str = '"') -> str:
    """Render active forced-nullable selectors for migration templates.

    Alembic templates are rendered as Python source code, not as structured
    JSON. This helper turns the active ``FORCE_FIELDS_NULLABLE`` context into a
    deterministic Python list literal containing ``(model_name, field_name)``
    tuples, while rejecting quote characters that would make the generated
    script ambiguous.

    Args:
        apostroph: Quote character to use around generated string literals.

    Returns:
        str: Python list literal that can be embedded in a migration file.

    Raises:
        RuntimeError: If any selector contains the quote character requested by
            the template.
    """
    items = tuple(sorted(FORCE_FIELDS_NULLABLE.get()))
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
    "with_force_fields_nullable",
]
