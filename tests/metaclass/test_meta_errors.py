import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import Manager, QuerySet
from saffier.db.connection import Database
from saffier.exceptions import ImproperlyConfigured

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class ObjectsManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(name__icontains="a")
        return queryset


async def test_improperly_configured_for_multiple_managers_on_abstract_class():
    with pytest.raises(ImproperlyConfigured) as raised:

        class BaseModel(saffier.Model):
            query = ObjectsManager()
            languages = ObjectsManager()

            class Meta:
                abstract = True
                registry = models

    assert raised.value.args[0] == "Multiple managers are not allowed in abstract classes."


async def test_improperly_configured_for_primary_key():
    with pytest.raises(ImproperlyConfigured) as raised:

        class BaseModel(saffier.Model):
            id = saffier.IntegerField(primary_key=False)
            query = ObjectsManager()
            languages = ObjectsManager()

            class Meta:
                registry = models

    assert (
        raised.value.args[0]
        == "Cannot create model BaseModel without explicit primary key if field 'id' is already present."
    )


async def test_improperly_configured_for_multiple_primary_keys():
    with pytest.raises(ImproperlyConfigured) as raised:

        class BaseModel(saffier.Model):
            name = saffier.IntegerField(primary_key=True)
            query = ObjectsManager()
            languages = ObjectsManager()

            class Meta:
                registry = models

    assert raised.value.args[0] == "Cannot create model BaseModel with multiple primary keys."
