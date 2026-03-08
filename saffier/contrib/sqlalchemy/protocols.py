from abc import abstractmethod
from typing import Any

import sqlalchemy

DIALECTS = {"postgres": "postgres"}


class BaseFieldProtocol(sqlalchemy.TypeDecorator):
    """Common protocol for Saffier SQLAlchemy type decorators.

    Concrete implementations must define how values are represented per dialect
    and converted when moving between Python and database rows.
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
        """Convert a database value back into the Python representation."""
        raise NotImplementedError("process_result_value must be implemented")
