import typing
from itertools import islice

import anyio

from saffier.db.constants import ITERATOR_CHUNK_SIZE

if typing.TYPE_CHECKING:
    from saffier.db.queryset import QuerySet


class BaseIeratbleModel:
    """
    Model based on Django's BaseIterable with typing on the top of it.
    """

    def __init__(
        self,
        queryset: typing.Type["QuerySet"],
        chunked_fetch: bool = False,
        chunck_size: int = ITERATOR_CHUNK_SIZE,
    ):
        self.queryset = queryset
        self.chunked_fetch = chunked_fetch
        self.chunk_size = chunck_size

    async def __anext__(self):
        return list(islice(self, self.chunk_size))

    async def _async_generator(self):
        sync_generator = self.__iter__()

        def next_slice(gen):
            return list(islice(gen, self.chunk_size))

        while True:
            chunk = await anyio.run(next_slice)(sync_generator)
            for item in chunk:
                yield item
            if len(chunk) < self.chunk_size:
                break

    def __aiter__(self):
        """
        We need the iterator to be async to match the async pattern.
        """
        return self._async_generator()


class IterableModel(BaseIeratbleModel):
    def __iter__(self):
        queryset = self.queryset
        for obj in queryset:
            yield obj
