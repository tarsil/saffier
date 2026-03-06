from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Hashable, Iterable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

if TYPE_CHECKING:
    from saffier.core.db.querysets.base import QuerySet

if sys.version_info >= (3, 11):  # pragma: no cover
    from typing import Self
else:  # pragma: no cover
    from typing_extensions import Self


@dataclass
class BasePage:
    content: list[Any]
    is_first: bool
    is_last: bool

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class Page(BasePage):
    current_page: int = 1
    next_page: int | None = None
    previous_page: int | None = None


PageType = TypeVar("PageType", bound=BasePage)


class BasePaginator(Generic[PageType]):
    order_by: tuple[str, ...]

    def __init__(
        self,
        queryset: QuerySet,
        page_size: int,
        next_item_attr: str = "",
        previous_item_attr: str = "",
    ) -> None:
        self._reverse_paginator: Self | None = None
        self.page_size = int(page_size)
        if page_size < 0:
            raise ValueError("page_size must be at least 0")
        if len(queryset._order_by) == 0:
            raise ValueError("You must pass a QuerySet with .order_by(*criteria)")

        self.next_item_attr = next_item_attr
        self.previous_item_attr = previous_item_attr
        self.queryset = (
            queryset.all() if (self.previous_item_attr or self.next_item_attr) else queryset
        )
        self.order_by = tuple(queryset._order_by)
        self._page_cache: dict[Hashable, PageType] = {}

    def clear_caches(self) -> None:
        self._page_cache.clear()
        if self._reverse_paginator:
            self._reverse_paginator = None

    async def get_amount_pages(self) -> int:
        if not self.page_size:
            return 1
        count, remainder = divmod(await self.get_total(), self.page_size)
        return count + (1 if remainder else 0)

    async def get_total(self) -> int:
        return await self.queryset.count()

    async def get_page(self) -> PageType:  # pragma: no cover
        raise NotImplementedError()

    async def get_page_as_dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return (await self.get_page(*args, **kwargs)).model_dump()

    def shall_drop_first(self, is_first: bool) -> bool:
        return bool(self.next_item_attr and not is_first)

    def convert_to_page(
        self, inp: Iterable[Any], /, is_first: bool, reverse: bool = False
    ) -> PageType:
        last_item: Any = None
        drop_first = self.shall_drop_first(is_first)
        result_list: list[Any] = []
        item_counter = 0

        for item in inp:
            if reverse:
                if self.next_item_attr:
                    setattr(item, self.next_item_attr, last_item)
                if last_item is not None and self.previous_item_attr:
                    setattr(last_item, self.previous_item_attr, item)
            else:
                if self.previous_item_attr:
                    setattr(item, self.previous_item_attr, last_item)
                if last_item is not None and self.next_item_attr:
                    setattr(last_item, self.next_item_attr, item)

            if (not drop_first and item_counter >= 1) or (drop_first and item_counter >= 2):
                result_list.append(last_item)
            last_item = item
            item_counter += 1

        min_size = self.page_size + 1
        if self.previous_item_attr and not is_first:
            min_size += 1

        is_last = bool(self.page_size == 0 or item_counter < min_size)

        if is_last and (
            (not drop_first and item_counter >= 1) or (drop_first and item_counter >= 2)
        ):
            if reverse and self.previous_item_attr:
                setattr(last_item, self.previous_item_attr, None)
            elif not reverse and self.next_item_attr:
                setattr(last_item, self.next_item_attr, None)
            result_list.append(last_item)

        if reverse:
            result_list.reverse()
            return cast(
                PageType,
                BasePage(content=result_list, is_first=is_last, is_last=is_first),
            )
        return cast(
            PageType,
            BasePage(content=result_list, is_first=is_first, is_last=is_last),
        )

    async def paginate_queryset(
        self,
        queryset: QuerySet,
        is_first: bool = True,
        prefill: Iterable[Any] | None = None,
    ) -> AsyncGenerator[BasePage, None]:
        container: list[Any] = []
        if prefill is not None:
            container.extend(prefill)

        page: PageType | None = None
        min_size = self.page_size + 1
        if self.previous_item_attr and not is_first:
            min_size += 1

        if getattr(queryset.database, "force_rollback", False):
            for item in await queryset:
                container.append(item)
                if self.page_size and len(container) >= min_size:
                    page = BasePaginator.convert_to_page(self, container, is_first=is_first)
                    yield page
                    if self.previous_item_attr and is_first:
                        min_size += 1
                    is_first = False
                    container = [page.content[-1], item] if self.previous_item_attr else [item]
        else:
            async for item in queryset:
                container.append(item)
                if self.page_size and len(container) >= min_size:
                    page = BasePaginator.convert_to_page(self, container, is_first=is_first)
                    yield page
                    if self.previous_item_attr and is_first:
                        min_size += 1
                    is_first = False
                    container = [page.content[-1], item] if self.previous_item_attr else [item]

        if page is None or not page.is_last:
            yield BasePaginator.convert_to_page(self, container, is_first=is_first)

    async def paginate(self) -> AsyncGenerator[PageType, None]:  # pragma: no cover
        raise NotImplementedError()

    async def paginate_as_dict(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for page in self.paginate(*args, **kwargs):
            yield page.model_dump()

    def get_reverse_paginator(self) -> Self:
        if self._reverse_paginator is None:
            self._reverse_paginator = type(self)(
                self.queryset.reverse(),
                page_size=self.page_size,
                next_item_attr=self.next_item_attr,
                previous_item_attr=self.previous_item_attr,
            )
            self._reverse_paginator._reverse_paginator = self
        return self._reverse_paginator


class NumberedPaginator(BasePaginator[Page]):
    async def paginate(self, start_page: int = 1) -> AsyncGenerator[Page, None]:
        query = self.queryset
        if start_page > 1:
            offset = self.page_size * (start_page - 1)
            if self.previous_item_attr:
                offset = max(offset - 1, 0)
            if offset > 0:
                query = query.offset(offset)

        counter = start_page
        async for page_obj in self.paginate_queryset(query, is_first=start_page == 1):
            yield Page(
                **page_obj.__dict__,
                next_page=None if page_obj.is_last else counter + 1,
                previous_page=None if page_obj.is_first else counter - 1,
                current_page=counter,
            )
            counter += 1

    def convert_to_page(
        self, inp: Iterable[Any], /, page: int, is_first: bool, reverse: bool = False
    ) -> Page:
        page_obj: BasePage = super().convert_to_page(inp, is_first=is_first, reverse=reverse)
        return Page(
            **page_obj.__dict__,
            current_page=page,
            next_page=None if page_obj.is_last else page + 1,
            previous_page=None if page_obj.is_first else page - 1,
        )

    async def _get_page(self, page: int, reverse: bool = False) -> Page:
        if page < 0 and self.page_size:
            return await self.get_reverse_paginator()._get_page(-page, reverse=True)
        offset = self.page_size * (page - 1)
        if self.previous_item_attr:
            offset = max(offset - 1, 0)

        query = self.queryset.offset(offset)
        if self.page_size:
            query = query.limit(self.page_size + 1)

        return self.convert_to_page(
            await query,
            page=page,
            is_first=offset == 0,
            reverse=reverse,
        )

    async def get_page(self, page: int = 1) -> Page:
        if page == 0 or not isinstance(page, int):
            raise ValueError(f"Invalid page parameter value: {page!r}")

        if self.page_size == 0:
            page = 1

        if page in self._page_cache:
            return cast(Page, self._page_cache[page])

        page_obj = await self._get_page(page=page)
        self._page_cache[page] = cast(PageType, page_obj)
        return page_obj


Paginator = NumberedPaginator
