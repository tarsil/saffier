import os

import pytest
from tests.settings import DATABASE_URL

import saffier
from esmerald import Esmerald
from saffier import Migrate
from saffier.testclient import DatabaseTestClient

pytestmark = pytest.mark.anyio
database = DatabaseTestClient(DATABASE_URL, drop_database=True)
models = saffier.Registry(database=database)

basedir = os.path.abspath(os.path.dirname(__file__))


class User(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


app = Esmerald(routes=[])
Migrate(app, registry=models)


async def add_user():
    await User.query.create(name="Test")
