from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    import sqlalchemy

    from saffier.core.connection.database import Database
    from saffier.core.db.models.managers import BaseManager
    from saffier.core.db.models.metaclasses import MetaInfo
    from saffier.core.db.models.model import Model


class DescriptiveMeta: ...


@runtime_checkable
class BaseModelType(Protocol):
    columns: ClassVar[sqlalchemy.sql.ColumnCollection]
    database: ClassVar[Database]
    table: ClassVar[sqlalchemy.Table]
    pkcolumns: ClassVar[Sequence[str]]
    pknames: ClassVar[Sequence[str]]
    query: ClassVar[BaseManager]
    query_related: ClassVar[BaseManager]
    meta: ClassVar[MetaInfo]
    Meta: ClassVar[DescriptiveMeta]
    __parent__: ClassVar[type[BaseModelType] | None]
    __is_proxy_model__: ClassVar[bool]
    __require_model_based_deletion__: ClassVar[bool]
    __reflected__: ClassVar[bool]

    @property
    def proxy_model(self) -> type[BaseModelType]: ...

    @property
    def identifying_db_fields(self) -> Any: ...

    @property
    def can_load(self) -> bool: ...

    def get_columns_for_name(self, name: str) -> Sequence[sqlalchemy.Column]: ...

    def identifying_clauses(self) -> Iterable[Any]: ...

    @classmethod
    def generate_proxy_model(cls) -> type[Model]: ...

    @classmethod
    def get_model_engine_name(cls) -> str | None: ...

    @classmethod
    def get_model_engine(cls) -> Any: ...

    @classmethod
    def get_engine_model_class(cls, *, mode: str = "projection") -> type[Any]: ...

    async def load(self, only_needed: bool = False) -> None: ...

    async def update(self, **kwargs: Any) -> BaseModelType: ...

    async def real_save(
        self,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | list[str] | None = None,
    ) -> BaseModelType: ...

    def to_engine_model(
        self, *, include: Any = None, exclude: Any = None, exclude_none: bool = False
    ) -> Any: ...

    def engine_dump(
        self, *, include: Any = None, exclude: Any = None, exclude_none: bool = False
    ) -> dict[str, Any]: ...

    def engine_dump_json(
        self,
        *,
        include: Any = None,
        exclude: Any = None,
        exclude_none: bool = False,
    ) -> str: ...

    @classmethod
    def table_schema(cls, schema: str | None = None) -> sqlalchemy.Table: ...

    @classmethod
    def build(cls, schema: str | None = None) -> sqlalchemy.Table: ...


__all__ = ["BaseModelType", "DescriptiveMeta"]
