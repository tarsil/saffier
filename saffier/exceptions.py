"""Exception types exposed by Saffier."""

import typing

from saffier.core.utils.base import BaseError


class SaffierException(Exception):
    """Base exception for Saffier runtime failures.

    Args:
        *args: Positional message fragments appended to the error text.
        detail: Optional structured detail used by higher-level callers.
    """

    def __init__(
        self,
        *args: typing.Any,
        detail: str = "",
    ):
        self.detail = detail
        super().__init__(*(str(arg) for arg in args if arg), self.detail)

    def __repr__(self) -> str:
        if self.detail:
            return f"{self.__class__.__name__} - {self.detail}"
        return self.__class__.__name__

    def __str__(self) -> str:
        return "".join(self.args).strip()


class ObjectNotFound(SaffierException):
    """Raised when a query expecting one row cannot find a match."""


DoesNotFound = ObjectNotFound


class MultipleObjectsReturned(SaffierException):
    """Raised when a query expecting one row matches multiple rows."""


class ValidationError(BaseError):
    """Raised when field or schema validation fails."""


class ImproperlyConfigured(SaffierException):
    """Raised when Saffier configuration is inconsistent or incomplete."""


class FieldDefinitionError(SaffierException):
    """Raised when a field declaration uses incompatible options."""


class ForeignKeyBadConfigured(SaffierException):
    """Raised when reverse relation wiring detects a conflicting foreign key."""


class RelationshipIncompatible(SaffierException):
    """Raised when relation helpers receive an object of the wrong model type."""


class DuplicateRecordError(SaffierException):
    """Raised when a create path detects a row that already exists."""


class RelationshipNotFound(SaffierException):
    """Raised when a requested relationship row or model cannot be resolved."""


class QuerySetError(SaffierException):
    """Raised when queryset construction or execution cannot proceed."""


class ModelReferenceError(SaffierException):
    """Raised when `RefForeignKey` references cannot be matched or persisted."""


class SchemaError(SaffierException):
    """Raised for schema-management failures."""


class SignalError(SaffierException):
    """Raised when signal registration or dispatch is invalid."""


class CommandEnvironmentError(SaffierException):
    """Raised when CLI discovery cannot determine the application environment."""


class MarshallFieldDefinitionError(FieldDefinitionError):
    """Raised when marshall field definitions are inconsistent."""


class DatabaseNotConnectedWarning(UserWarning):
    """Warning emitted when database-dependent code runs without a live connection."""


class SuspiciousFileOperation(SaffierException):
    """Raised when a storage operation escapes an allowed path boundary."""


class FileOperationError(SaffierException):
    """Raised when storage backends fail to complete a file operation."""


class InvalidStorageError(ImproperlyConfigured):
    """Raised when a configured storage backend cannot be loaded."""
