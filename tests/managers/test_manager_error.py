from typing import ClassVar

import pytest

import saffier
from saffier import Manager
from saffier.core.db.querysets.base import QuerySet
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class UserManager(Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_admin=False)


def test_raise_improperly_configured_on_missing_annotation() -> None:
    with pytest.raises(ImproperlyConfigured) as raised:

        class User(saffier.Model):
            username = saffier.CharField(max_length=150)
            is_admin = saffier.BooleanField(default=True)

            mang = UserManager()

            class Meta:
                registry = models

    assert raised.value.args[0] == (
        "Managers must be ClassVar type annotated and 'mang' is not or not correctly annotated."
    )


def test_raise_improperly_configured_on_wrong_annotation() -> None:
    with pytest.raises(ImproperlyConfigured) as raised:

        class User(saffier.Model):
            username = saffier.CharField(max_length=150)
            is_admin = saffier.BooleanField(default=True)

            mang: Manager = UserManager()

            class Meta:
                registry = models

    assert raised.value.args[0] == (
        "Managers must be ClassVar type annotated and 'mang' is not or not correctly annotated."
    )


def test_accepts_classvar_manager_annotation() -> None:
    class User(saffier.Model):
        username = saffier.CharField(max_length=150)
        is_admin = saffier.BooleanField(default=True)

        mang: ClassVar[Manager] = UserManager()

        class Meta:
            registry = models

    assert isinstance(User.mang, UserManager)
