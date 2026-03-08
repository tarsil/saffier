import os

import pytest
from ravyn import Ravyn

import saffier
from saffier import Migrate
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio
database = DatabaseTestClient(DATABASE_URL, drop_database=True)
models = saffier.Registry(database=database)

basedir = os.path.abspath(os.path.dirname(__file__))


class AppUser(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


app = Ravyn(routes=[])
Migrate(app, registry=models)
