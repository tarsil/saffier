from __future__ import annotations

import sys
import types
import warnings
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar, cast

import sqlalchemy

from saffier.core.connection.database import Database
from saffier.core.db.context_vars import get_schema, set_schema

if TYPE_CHECKING:
    from saffier import Model, QuerySet, ReflectModel

_sentinel = object()
_undefined = object()

_SaffierModel = TypeVar("_SaffierModel", bound="Model")
ReflectSaffierModel = TypeVar("ReflectSaffierModel", bound="ReflectModel")

SaffierModel = _SaffierModel | ReflectSaffierModel


class QuerySetPropsMixin:
    """Property helpers shared by queryset implementations.

    The mixin keeps common accessors such as database, table, and primary-key
    metadata in one place so queryset subclasses stay focused on query logic.
    """

    @property
    def database(self) -> Database:
        if getattr(self, "_database", None) is None:
            return cast("Database", self.model_class.database)
        return self._database

    @database.setter
    def database(self, value: Database) -> None:
        self._database = value

    @property
    def table(self) -> sqlalchemy.Table:
        if getattr(self, "_table", None) is None:
            return cast("sqlalchemy.Table", self.model_class.table)
        return self._table

    @table.setter
    def table(self, value: sqlalchemy.Table) -> None:
        self._table = value

    @property
    def pkname(self) -> Any:
        return self.model_class.pkname  # type: ignore

    @property
    def pknames(self) -> Any:
        return self.model_class.pknames  # type: ignore

    @property
    def pkcolumns(self) -> Any:
        return self.model_class.pkcolumns  # type: ignore

    @property
    def is_m2m(self) -> bool:
        return bool(self.model_class.meta.is_multi)

    @property
    def m2m_related(self) -> str:
        return self._m2m_related

    @m2m_related.setter
    def m2m_related(self, value: str) -> None:
        self._m2m_related = value


class TenancyMixin:
    """Mixin that adds schema and database rebinding helpers to querysets.

    It powers `.using()` for multi-database and multi-schema applications,
    including tenant-aware schema selection.
    """

    def using(
        self,
        _positional: Any = _sentinel,
        *,
        database: str | Database | None | Any = _undefined,
        schema: str | None | bool | Any = _undefined,
    ) -> QuerySet:
        if _positional is not _sentinel:
            warnings.warn(
                "Passing positional arguments to using is deprecated. Use schema= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            schema = _positional

        queryset = cast("QuerySet", self._clone())

        if database is not _undefined:
            if isinstance(database, Database):
                queryset.database = database
            elif database is None:
                queryset.database = self.model_class.meta.registry.database
            else:
                assert database in self.model_class.meta.registry.extra, (
                    f"`{database}` is not in the connections extra of the model"
                    f"`{self.model_class.__name__}` registry"
                )
                queryset.database = self.model_class.meta.registry.extra[database]

        if schema is not _undefined:
            queryset.using_schema = None if schema is False else schema
            if schema is False:
                queryset.table = self.model_class.table
            else:
                queryset.table = self.model_class.table_schema(
                    cast("str | None", queryset.using_schema)
                )

        return queryset

    def using_with_db(
        self, connection_name: str, schema: str | None | bool | Any = _undefined
    ) -> QuerySet:
        warnings.warn(
            "'using_with_db' is deprecated in favor of 'using' with schema, database arguments.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.using(database=connection_name, schema=schema)


def activate_schema(schema: str) -> None:
    warnings.warn(
        "`activate_schema` is deprecated use `with_schema` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    set_schema(schema)


def deactivate_schema() -> None:
    warnings.warn(
        "`activate_schema` is deprecated use `with_schema` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    set_schema(None)


def deativate_schema() -> None:
    deactivate_schema()


@contextmanager
def with_schema(schema: str | None):
    previous_schema = get_schema()
    set_schema(schema)
    try:
        yield
    finally:
        set_schema(previous_schema)


def _install_legacy_submodule(name: str, exports: dict[str, Any]) -> None:
    module_name = f"{__name__}.{name}"
    module = types.ModuleType(module_name)
    module.__dict__.update(exports)
    module.__all__ = sorted(exports)
    sys.modules[module_name] = module


def _install_lazy_submodule(name: str, attr_name: str, import_path: str) -> None:
    module_name = f"{__name__}.{name}"
    module = types.ModuleType(module_name)

    def __getattr__(attr: str) -> Any:
        if attr != attr_name:
            raise AttributeError(attr)
        module_name_inner, _, object_name = import_path.rpartition(".")
        imported_module = __import__(module_name_inner, fromlist=[object_name])
        value = getattr(imported_module, object_name)
        module.__dict__[attr_name] = value
        return value

    module.__getattr__ = __getattr__  # type: ignore[attr-defined]
    module.__all__ = [attr_name]
    sys.modules[module_name] = module


__path__ = []  # Allow `saffier.core.db.querysets.mixins.*` compatibility imports.

_install_legacy_submodule("queryset_props", {"QuerySetPropsMixin": QuerySetPropsMixin})
_install_legacy_submodule(
    "tenancy",
    {
        "TenancyMixin": TenancyMixin,
        "activate_schema": activate_schema,
        "deactivate_schema": deactivate_schema,
        "deativate_schema": deativate_schema,
        "with_schema": with_schema,
    },
)
_install_lazy_submodule(
    "combined",
    "CombinedQuerySet",
    "saffier.core.db.querysets.base.CombinedQuerySet",
)


__all__ = [
    "QuerySetPropsMixin",
    "ReflectSaffierModel",
    "SaffierModel",
    "TenancyMixin",
    "activate_schema",
    "deactivate_schema",
    "deativate_schema",
    "with_schema",
]
