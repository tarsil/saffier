from abc import abstractmethod
from typing import Any, Protocol

import sqlalchemy
from typing_extensions import Protocol, runtime_checkable

DIALECTS = {"postgres": "postgres"}


class BaseFieldProtocol(sqlalchemy.TypeDecorator):
    """
    When implementing a field representation from SQLAlchemy, the protocol will be enforced
    """

    impl: Any
    cache_ok: bool

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
