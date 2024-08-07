import typing

from saffier.core.utils.base import BaseError


class SaffierException(Exception):
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


class ObjectNotFound(SaffierException): ...


DoesNotFound = ObjectNotFound


class MultipleObjectsReturned(SaffierException): ...


class ValidationError(BaseError): ...


class ImproperlyConfigured(SaffierException): ...


class ForeignKeyBadConfigured(SaffierException): ...


class RelationshipIncompatible(SaffierException): ...


class DuplicateRecordError(SaffierException): ...


class RelationshipNotFound(SaffierException): ...


class QuerySetError(SaffierException): ...


class ModelReferenceError(SaffierException): ...


class SchemaError(SaffierException): ...


class SignalError(SaffierException): ...


class CommandEnvironmentError(SaffierException): ...
