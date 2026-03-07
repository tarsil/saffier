from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saffier.core.db.querysets.base import QuerySet
    from saffier.core.db.querysets.types import tables_and_models_type


class ResultParser:
    def __init__(self, queryset: QuerySet):
        self.queryset = queryset

    async def row_to_model(
        self,
        row: Any,
        tables_and_models: tables_and_models_type,
    ) -> tuple[Any, Any]:
        result = await self.queryset._hydrate_row(
            self.queryset,
            row,
            tables_and_models,
            is_only_fields=bool(self.queryset._only),
            is_defer_fields=bool(self.queryset._defer),
        )
        return result, self.queryset._embed_parent_in_result(result)

    async def batch_to_models(
        self,
        rows: Sequence[Any],
        tables_and_models: tables_and_models_type,
        _prefetches: Any = None,
        _cache: Any = None,
    ) -> list[tuple[Any, Any]]:
        return [await self.row_to_model(row, tables_and_models) for row in rows]


__all__ = ["ResultParser"]
