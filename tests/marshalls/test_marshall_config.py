from __future__ import annotations

from typing import ClassVar

import pytest

import saffier
from saffier.exceptions import MarshallFieldDefinitionError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def build_registry() -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL))


def test_missing_marshall_config_raises() -> None:
    with pytest.raises(MarshallFieldDefinitionError, match="marshall_config"):

        class BrokenMarshall(saffier.Marshall):
            details = saffier.MarshallMethodField(str)


def test_fields_and_exclude_are_mutually_exclusive() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100, null=True)
        email = saffier.EmailField(max_length=100, null=True)

        class Meta:
            registry = registry_obj

    with pytest.raises(AssertionError, match="Use either 'fields' or 'exclude', not both."):

        class BrokenMarshall(saffier.Marshall):
            marshall_config = saffier.ConfigMarshall(
                model=User,
                fields=["email"],
                exclude=["name"],
            )


def test_fields_or_exclude_must_be_declared() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100, null=True)

        class Meta:
            registry = registry_obj

    with pytest.raises(AssertionError, match="Either 'fields' or 'exclude' must be declared."):

        class BrokenMarshall(saffier.Marshall):
            marshall_config = saffier.ConfigMarshall(model=User)


def test_missing_method_getter_raises() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        email = saffier.EmailField(max_length=100, null=True)

        class Meta:
            registry = registry_obj

    with pytest.raises(
        MarshallFieldDefinitionError,
        match="Field 'details' declared but no 'get_details' found in 'BrokenMarshall'.",
    ):

        class BrokenMarshall(saffier.Marshall):
            marshall_config = saffier.ConfigMarshall(model=User, fields=["email"])
            details = saffier.MarshallMethodField(str)


def test_incomplete_marshall_raises_when_instance_is_requested() -> None:
    registry_obj = build_registry()

    class Profile(saffier.Model):
        name = saffier.CharField(max_length=100)
        email = saffier.EmailField(max_length=100)

        class Meta:
            registry = registry_obj

    class ProfileMarshall(saffier.Marshall):
        marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
            model=Profile,
            fields=["email"],
        )

    with pytest.raises(
        RuntimeError,
        match=r"'ProfileMarshall' is an incomplete Marshall\..*\[name\]\.",
    ):
        _ = ProfileMarshall(email="foo@example.com").instance


def test_missing_classvar_annotation_raises() -> None:
    registry_obj = build_registry()

    class Profile(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    with pytest.raises(
        MarshallFieldDefinitionError,
        match="'marshall_config' is part of the fields of 'BrokenMarshall'.",
    ):

        class BrokenMarshall(saffier.Marshall):
            marshall_config: saffier.ConfigMarshall = saffier.ConfigMarshall(
                model=Profile,
                fields=["__all__"],
            )


def test_primary_key_read_only_and_exclude_autoincrement_are_applied() -> None:
    registry_obj = build_registry()

    class Product(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class ProductMarshall(saffier.Marshall):
        marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
            model=Product,
            fields=["__all__"],
            primary_key_read_only=True,
            exclude_autoincrement=True,
        )

    assert "id" not in ProductMarshall.model_fields
    assert "name" in ProductMarshall.model_fields


def test_public_marshalls_namespace_is_exposed() -> None:
    assert saffier.marshalls.Marshall is saffier.Marshall
    assert saffier.marshalls.MarshallField is saffier.MarshallField
    assert saffier.marshalls.MarshallMethodField is saffier.MarshallMethodField
