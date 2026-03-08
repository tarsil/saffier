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
        """Return the dialect-specific SQLAlchemy type implementation.

        Args:
            dialect (Any): SQLAlchemy dialect currently compiling the type.

        Returns:
            Any: Dialect-specific SQLAlchemy type object.
        """
        raise NotImplementedError("load_dialect_impl must be implemented")

    @abstractmethod
    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Convert one Python value before sending it to the database.

        Args:
            value (Any): Python value about to be bound to a statement.
            dialect (Any): SQLAlchemy dialect handling the bind step.

        Returns:
            Any: Serialized value suitable for the target database driver.
        """
        raise NotImplementedError("process_bind_param must be implemented")

    @abstractmethod
    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Convert one database value back into the Python representation.

        Args:
            value (Any): Raw database value returned by the driver.
            dialect (Any): SQLAlchemy dialect handling the result step.

        Returns:
            Any: Deserialized Python value exposed on the Saffier model field.
        """
        raise NotImplementedError("process_result_value must be implemented")
