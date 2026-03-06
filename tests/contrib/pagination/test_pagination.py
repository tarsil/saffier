import pytest

import saffier
from saffier.contrib.pagination import CursorPaginator, Paginator
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class IntCounter(saffier.Model):
    id: int = saffier.IntegerField(primary_key=True, autoincrement=False)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_numbered_pagination():
    await IntCounter.query.delete()
    await IntCounter.query.bulk_create([{"id": i} for i in range(100)])
    paginator = Paginator(
        IntCounter.query.order_by("id"),
        page_size=30,
        next_item_attr="next",
        previous_item_attr="prev",
    )
    assert await paginator.get_total() == 100

    pages = [page async for page in paginator.paginate()]
    assert len(pages) == 4
    assert pages[0].content[0].id == 0
    assert pages[0].content[-1].id == 29
    assert pages[-1].content[-1].id == 99
    assert pages[0].is_first is True
    assert pages[-1].is_last is True
    assert pages[0].content[1].prev is pages[0].content[0]
    assert pages[0].content[0].next is pages[0].content[1]

    reverse_page = await paginator.get_page(-1)
    assert reverse_page.content[-1].id == 99
    assert reverse_page.current_page == 1


async def test_cursor_pagination():
    await IntCounter.query.delete()
    await IntCounter.query.bulk_create([{"id": i} for i in range(100)])
    paginator = CursorPaginator(
        IntCounter.query.order_by("id"),
        page_size=30,
        next_item_attr="next",
        previous_item_attr="prev",
    )
    first_page = await paginator.get_page()
    assert first_page.is_first
    assert first_page.next_cursor == 29
    assert first_page.content[0].prev is None

    second_page = await paginator.get_page(first_page.next_cursor)
    assert second_page.content[0].id == 30
    assert second_page.is_first is False

    backward_page = await paginator.get_page(first_page.next_cursor, backward=True)
    assert backward_page.is_first is True
    assert backward_page.content[0].id == 0
    assert backward_page.content[-1].id == 29


async def test_paginate_as_dict():
    await IntCounter.query.delete()
    await IntCounter.query.bulk_create([{"id": i} for i in range(10)])
    paginator = CursorPaginator(IntCounter.query.order_by("id"), page_size=4)
    pages_as_objects = [page.model_dump() async for page in paginator.paginate()]
    pages_as_dict = [page async for page in paginator.paginate_as_dict()]
    assert pages_as_objects == pages_as_dict
