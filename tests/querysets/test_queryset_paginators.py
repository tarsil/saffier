import pytest

import saffier
from saffier.contrib.pagination import CursorPaginator, NumberedPaginator
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)

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


async def test_queryset_paginator_helpers():
    await Product.query.bulk_create([{"name": f"product-{i}"} for i in range(5)])
    queryset = Product.query.order_by("id")

    numbered = queryset.paginator(page_size=2)
    cursor = queryset.cursor_paginator(page_size=2)

    assert isinstance(numbered, NumberedPaginator)
    assert isinstance(cursor, CursorPaginator)

    first_numbered = await numbered.get_page(1)
    first_cursor = await cursor.get_page()

    assert len(first_numbered.content) == 2
    assert len(first_cursor.content) == 2
