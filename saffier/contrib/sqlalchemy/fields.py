import ipaddress
import uuid
from typing import Any

import sqlalchemy
from orjson import loads

from saffier.contrib.sqlalchemy.protocols import BaseFieldProtocol
from saffier.contrib.sqlalchemy.types import SubList

DIALECTS = {"postgres": "postgres", "postgresql": "postgresql"}


class GUID(BaseFieldProtocol):
    """SQLAlchemy type decorator that stores UUID values portably.

    PostgreSQL uses the native UUID type, while other backends fall back to a
    fixed-width character representation.
    """

    impl: Any = sqlalchemy.CHAR
    cache_ok: bool = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name != DIALECTS["postgres"]:
            return dialect.type_descriptor(sqlalchemy.CHAR(32))
        return dialect.type_descriptor(sqlalchemy.dialects.postgresql.UUID())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name != DIALECTS["postgres"]:
            return value.hex
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value


class IPAddress(BaseFieldProtocol):
    """SQLAlchemy type decorator for IPv4 and IPv6 addresses."""

    impl: str = sqlalchemy.CHAR  # type: ignore
    cache_ok: bool = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name not in DIALECTS:
            return dialect.type_descriptor(sqlalchemy.CHAR(45))
        return dialect.type_descriptor(sqlalchemy.dialects.postgresql.INET())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is not None:
            return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            value = ipaddress.ip_address(value)
        return value


class List(BaseFieldProtocol):
    """SQLAlchemy type decorator for list-like values stored as text/varchar.

    PostgreSQL gets a varchar representation, while other databases use a
    delimited string fallback.
    """

    impl: Any = sqlalchemy.TEXT
    cache_ok: bool = True

    def __init__(self, impl: Any = sqlalchemy.TEXT, cache_ok: bool = True, **kwargs: Any) -> None:
        self.delimiter = kwargs.pop("delimiter", ",")
        super().__init__(**kwargs)
        self.impl = impl
        self.cache_ok = cache_ok

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name != DIALECTS["postgres"]:
            return dialect.type_descriptor(sqlalchemy.CHAR(5000))
        return dialect.type_descriptor(sqlalchemy.dialects.postgresql.VARCHAR())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is not None:
            value = loads(value)
            return list(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return SubList(self.delimiter)
        if isinstance(value, list):
            return value
        return SubList(self.delimiter, value.split(self.delimiter))
