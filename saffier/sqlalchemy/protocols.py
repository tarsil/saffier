import ipaddress
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Protocol

import sqlalchemy
from pydantic import Field
from typing_extensions import Protocol, runtime_checkable

DIALECTS = {"postgres": "postgres"}


@runtime_checkable
class FieldProtocol(Protocol):
    """
    Protocol implementation for a Field coming from SQLAlchemy
    """

    impl: Any
    cache_ok: bool

    def load_dialect_impl(self, dialect: Any) -> Any:
        ...

    def process_bind_param(self, value: Any, dialect: Any) -> str:
        ...

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        ...


class BaseFieldProtocol(sqlalchemy.TypeDecorator, FieldProtocol):
    """
    When implementing a field representation from SQLAlchemy, the protocol will be enforced
    """

    @abstractmethod
    def load_dialect_impl(self, dialect: Any) -> Any:
        raise NotImplemented("load_dialect_impl must be implemented")

    @abstractmethod
    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        raise NotImplemented("process_bind_param must be implemented")

    @abstractmethod
    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """
        Processes the value coming from the database in a column-row style.
        """
        raise NotImplemented("process_result_value must be implemented")
