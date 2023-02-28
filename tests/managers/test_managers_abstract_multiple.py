import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import Manager
from saffier.testclient import DatabaseTestClient as Database
from saffier.db.queryset import QuerySet
from saffier.exceptions import ImproperlyConfigured

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class ObjectsManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(is_active=True)
        return queryset


class LanguageManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(language="EN")
        return queryset


async def test_inherited_abstract_base_model_managers_raises_error_on_multiple():
    with pytest.raises(ImproperlyConfigured) as raised:

        class BaseModel(saffier.Model):
            query = ObjectsManager()
            languages = LanguageManager()

            class Meta:
                abstract = True
                registry = models

    assert raised.value.args[0] == "Multiple managers are not allowed in abstract classes."
