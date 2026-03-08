from __future__ import annotations

from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from saffier.exceptions import MultipleObjectsReturned, ObjectNotFound

from .compiler import QueryCompiler
from .parser import ResultParser

if TYPE_CHECKING:
    import sqlalchemy

    from saffier.core.db.querysets.base import BaseQuerySet


_current_row_holder: ContextVar[list[sqlalchemy.Row | None] | None] = ContextVar(
    "_current_row_holder",
    default=None,
)


def get_current_row():
    row_holder = _current_row_holder.get()
    if not row_holder:
        return None
    return row_holder[0]


class QueryExecutor:
    """
    Compatibility facade around Saffier's queryset execution helpers.
    """

    def __init__(
        self,
        queryset: BaseQuerySet,
        compiler: QueryCompiler | None = None,
        parser: ResultParser | None = None,
    ):
        self.queryset = queryset
        self.compiler = compiler or QueryCompiler(queryset)
        self.parser = parser or ResultParser(queryset)

    async def iterate(self, fetch_all_at_once: bool = False) -> AsyncGenerator[Any, None]:
        async for item in self.queryset._execute_iterate(fetch_all_at_once=fetch_all_at_once):
            yield item

    async def get_one(self) -> tuple[Any, Any]:
        expression, tables_and_models = await self.queryset.as_select_with_tables()
        rows = await self.queryset.database.fetch_all(expression.limit(2))
        if not rows:
            raise ObjectNotFound()
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        current_row = [rows[0]]
        token = _current_row_holder.set(current_row)
        try:
            return await self.parser.row_to_model(rows[0], tables_and_models)
        finally:
            _current_row_holder.reset(token)


__all__ = ["QueryExecutor", "get_current_row"]
