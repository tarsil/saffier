from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from saffier.core.db.querysets.base import BaseQuerySet


class QueryCompiler:
    """
    Thin compatibility wrapper around Saffier's in-queryset compiler.
    """

    def __init__(self, queryset: BaseQuerySet):
        self.queryset = queryset

    async def build_select(self):
        return await self.queryset.as_select_with_tables()


__all__ = ["QueryCompiler"]
