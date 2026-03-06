from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:  # pragma: nocover
    from saffier import Model, QuerySet, ReflectModel


_SaffierModel = TypeVar("_SaffierModel", bound="Model")
ReflectSaffierModel = TypeVar("ReflectSaffierModel", bound="ReflectModel")

SaffierModel = _SaffierModel | ReflectSaffierModel


@runtime_checkable
class QuerySetProtocol(Protocol):
    """Defines the what needs to be implemented when using the ManyRelationProtocol"""

    def filter(self, **kwargs: Any) -> "QuerySet": ...

    def exclude(self, **kwargs: "Model") -> "QuerySet": ...

    def lookup(self, **kwargs: Any) -> "QuerySet": ...

    def order_by(self, columns: list | str) -> "QuerySet": ...

    def reverse(self) -> "QuerySet": ...

    def limit(self, limit_count: int) -> "QuerySet": ...

    def offset(self, offset: int) -> "QuerySet": ...

    def group_by(self, group_by: list | str) -> "QuerySet": ...

    def distinct(self, distinct_on: list | str) -> "QuerySet": ...

    def select_related(self, related: list | str) -> "QuerySet": ...

    async def exists(self) -> bool: ...

    async def count(self) -> int: ...

    async def get_or_none(self, **kwargs: Any) -> SaffierModel | None: ...

    async def all(self, **kwargs: Any) -> Sequence[SaffierModel | None]: ...

    async def get(self, **kwargs: Any) -> SaffierModel: ...

    async def first(self, **kwargs: Any) -> SaffierModel | None: ...

    async def last(self, **kwargs: Any) -> SaffierModel | None: ...

    async def create(self, **kwargs: Any) -> SaffierModel: ...

    async def bulk_create(self, objs: Sequence[list[dict[Any, Any]]]) -> None: ...

    async def bulk_update(self, objs: Sequence[list[SaffierModel]], fields: list[str]) -> None: ...

    async def delete(self) -> None: ...

    async def update(self, **kwargs: Any) -> None: ...

    async def values(
        self,
        fields: Sequence[str] | str | None,
        exclude: Sequence[str] | set[str],
        exclude_none: bool,
        flatten: bool,
        **kwargs: Any,
    ) -> list[Any]: ...

    async def values_list(
        self,
        fields: Sequence[str] | str | None,
        exclude: Sequence[str] | set[str],
        exclude_none: bool,
        flat: bool,
    ) -> list[Any]: ...

    async def get_or_create(
        self,
        _defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[SaffierModel, bool]: ...

    async def update_or_create(
        self, defaults: Any, **kwargs: Any
    ) -> tuple[SaffierModel, bool]: ...

    async def contains(self, instance: SaffierModel) -> bool: ...

    def union(self, other: "QuerySet", *, all: bool = ...) -> "QuerySet": ...

    def union_all(self, other: "QuerySet") -> "QuerySet": ...

    def intersect(self, other: "QuerySet", *, all: bool = ...) -> "QuerySet": ...

    def intersect_all(self, other: "QuerySet") -> "QuerySet": ...

    def except_(self, other: "QuerySet", *, all: bool = ...) -> "QuerySet": ...

    def except_all(self, other: "QuerySet") -> "QuerySet": ...

    def select_for_update(
        self,
        *,
        nowait: bool = ...,
        skip_locked: bool = ...,
        read: bool = ...,
        key_share: bool = ...,
        of: Sequence[type["Model"]] | None = ...,
    ) -> "QuerySet": ...

    def transaction(self, *, force_rollback: bool = ..., **kwargs: Any) -> Any: ...
