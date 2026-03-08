from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Generator, Iterable, Sequence
from itertools import islice
from typing import TypeVar

from saffier.conf import settings

T = TypeVar("T")


def batched(iterable: Iterable[T], n: int) -> Generator[tuple[T, ...], None, None]:
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


async def run_concurrently(coros: Sequence[Awaitable[T]], limit: int | None = None) -> list[T]:
    """
    Execute awaitables concurrently while respecting runtime concurrency settings.
    """
    if not coros:
        return []

    enabled = getattr(settings, "orm_concurrency_enabled", True)
    effective_limit = (
        limit if limit is not None else getattr(settings, "orm_concurrency_limit", None)
    )
    if not enabled:
        effective_limit = 1

    if effective_limit == 1:
        results: list[T] = []
        for coro in coros:
            results.append(await coro)
        return results

    if effective_limit is None or effective_limit <= 0:
        return list(await asyncio.gather(*coros))

    results: list[T] = []
    for batch in batched(coros, effective_limit):
        results.extend(await asyncio.gather(*batch))
    return results


__all__ = ["batched", "run_concurrently"]
