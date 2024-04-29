import pytest
from esmerald import Esmerald

import saffier
from saffier import Migrate, Registry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = Registry(database=database)
nother = Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models
        abstract = True


class Profile(User):
    age = saffier.IntegerField()

    class Meta:
        registry = models
        tablename = "profiles"


class Contact(Profile):
    age = saffier.CharField(max_length=255)
    address = saffier.CharField(max_length=255)

    class Meta:
        registry = models
        tablename = "contacts"


class ReflectedContact(saffier.ReflectModel):
    age = saffier.CharField(max_length=255)
    address = saffier.CharField(max_length=255)

    class Meta:
        tablename = "contacts"
        registry = models


def test_migrate_with_model_apps():
    app = Esmerald()
    models.models = {}

    assert len(models.models) == 0

    migrate = Migrate(app=app, registry=models, model_apps={"tests": "tests.test_migrate"})

    assert len(models.models) == 2
    assert len(migrate.registry.models) == 2
