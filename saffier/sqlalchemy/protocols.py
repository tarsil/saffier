from abc import abstractmethod
from typing import Any

import sqlalchemy

DIALECTS = {"postgres": "postgres"}


class BaseFieldProtocol(sqlalchemy.TypeDecorator):  # type: ignore
    """
    When implementing a field representation from SQLAlchemy, the protocol will be enforced
    """

    impl: Any
    cache_ok: bool

    @abstractmethod
    def load_dialect_impl(self, dialect: Any) -> Any:
        raise NotImplementedError("load_dialect_impl must be implemented")

    @abstractmethod
    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        raise NotImplementedError("process_bind_param must be implemented")

    @abstractmethod
    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """
        Processes the value coming from the database in a column-row style.
        """
        raise NotImplementedError("process_result_value must be implemented")
