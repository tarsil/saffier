from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from saffier.core.db.querysets.base import BaseQuerySet


class QueryCompiler:
    """Compatibility facade around queryset SQL compilation helpers.

    Older integrations expect a dedicated compiler object; Saffier now compiles
    queries inside the queryset itself, and this wrapper preserves that API.
    """

    def __init__(self, queryset: BaseQuerySet):
        self.queryset = queryset

    async def build_select(self):
        return await self.queryset.as_select_with_tables()


__all__ = ["QueryCompiler"]
