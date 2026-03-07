import asyncio

import pytest

import saffier
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, force_rollback=False, full_isolation=False)
models = saffier.Registry(database=database, with_content_type=True)


class Organisation(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Company(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


async def test_iterate_content_types_with_async_tasks():
    company = await Company.query.create(name="iterate-company")
    organisation = await Organisation.query.create(name="iterate-organisation")

    assert company.content_type.name == "Company"
    assert organisation.content_type.name == "Organisation"
    assert await models.content_type.query.count() == 2

    resolved = [
        await asyncio.create_task(content_type.get_instance())
        async for content_type in models.content_type.query.all()
    ]

    assert company in resolved
    assert organisation in resolved
