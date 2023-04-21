import pytest

import saffier
from saffier import Manager, QuerySet
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

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


@pytest.mark.parametrize("_type,value", [("int", 1), ("dict", {"name": "test"}), ("set", set())])
async def test_improperly_configured_for_unique_together(_type, value):
    with pytest.raises(ImproperlyConfigured) as raised:

        class BaseModel(saffier.Model):
            name = saffier.IntegerField()
            query = ObjectsManager()
            languages = ObjectsManager()

            class Meta:
                registry = models
                unique_together = value

    assert raised.value.args[0] == f"unique_together must be a tuple or list. Got {_type} instead."


@pytest.mark.parametrize(
    "value",
    [(1, dict), ["str", 1, set], [1], [dict], [set], [set, dict, list, tuple]],
    ids=[
        "int-and-dict",
        "str-int-set",
        "list-of-int",
        "list-of-dict",
        "list-of-set",
        "list-of-set-dict-tuple-and-lists",
    ],
)
async def test_value_error_for_unique_together(value):
    with pytest.raises(ValueError) as raised:

        class BaseModel(saffier.Model):
            name = saffier.IntegerField()
            query = ObjectsManager()
            languages = ObjectsManager()

            class Meta:
                registry = models
                unique_together = value

    assert (
        raised.value.args[0]
        == "The values inside the unique_together must be a string, a tuple of strings or an instance of UniqueConstraint."
    )


def test_raises_value_error_on_wrong_type():
    with pytest.raises(ValueError) as raised:

        class User(saffier.Model):
            name = saffier.CharField(max_length=255)

            class Meta:
                registry = models
                indexes = ["name"]

    assert raised.value.args[0] == "Meta.indexes must be a list of Index types."
