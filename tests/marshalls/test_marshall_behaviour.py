from __future__ import annotations

from typing import Any, ClassVar

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

models = saffier.Registry(database=Database(url=DATABASE_URL))


class User(saffier.Model):
    name = saffier.CharField(max_length=100, null=True)
    email = saffier.EmailField(max_length=100, null=True)
    language = saffier.CharField(max_length=200, null=True)
    description = saffier.TextField(max_length=5000, null=True)

    class Meta:
        registry = models

    def get_name(self) -> str:
        return f"Details about {self.name}"

    @property
    def upper_name(self) -> str | None:
        return None if self.name is None else self.name.upper()


class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name", "email", "language", "description"],
    )
    details = saffier.MarshallMethodField(str)
    mirrored_name = saffier.MarshallField(str, source="name")
    upper_name = saffier.MarshallField(str, source="upper_name")
    extra_context = saffier.MarshallMethodField(dict[str, Any])
    shall_save = saffier.MarshallField(bool, default=False, exclude=True)

    def get_details(self, instance: User) -> str:
        return instance.get_name()

    def get_extra_context(self, instance: User) -> dict[str, Any]:
        return self.context


class AsyncMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name"],
    )
    async_details = saffier.MarshallMethodField(str)

    async def get_async_details(self, instance: User) -> str:
        return instance.get_name()


def test_marshall_context_and_custom_fields() -> None:
    marshalled = UserMarshall(
        name="Saffier",
        email="saffier@ravyn.dev",
        language="EN",
        description="Python-native ORM",
        context={"scope": "test"},
    )

    assert marshalled.model_dump() == {
        "name": "Saffier",
        "email": "saffier@ravyn.dev",
        "language": "EN",
        "description": "Python-native ORM",
        "details": "Details about Saffier",
        "mirrored_name": "Saffier",
        "upper_name": "SAFFIER",
        "extra_context": {"scope": "test"},
    }
    assert marshalled.shall_save is False
    assert "shall_save" not in marshalled.model_dump()
    assert "shall_save" in UserMarshall.model_fields
    assert "shall_save" not in UserMarshall.__custom_fields__


def test_marshall_from_instance_populates_source_and_method_fields() -> None:
    user = User(
        name="Edgy",
        email="edgy@ravyn.dev",
        language="EN",
        description="Parity test",
    )

    marshalled = UserMarshall(instance=user)

    assert marshalled.model_dump() == {
        "name": "Edgy",
        "email": "edgy@ravyn.dev",
        "language": "EN",
        "description": "Parity test",
        "details": "Details about Edgy",
        "mirrored_name": "Edgy",
        "upper_name": "EDGY",
        "extra_context": {},
    }
    assert marshalled.instance is user
    assert marshalled.has_instance is True
    assert marshalled.meta is User.meta


def test_model_dump_exclude_unset_and_schema() -> None:
    marshalled = UserMarshall(name="Only name")

    assert marshalled.model_dump(exclude_unset=True) == {
        "name": "Only name",
        "details": "Details about Only name",
        "mirrored_name": "Only name",
        "upper_name": "ONLY NAME",
        "extra_context": {},
    }

    schema = UserMarshall.model_json_schema()
    assert "shall_save" not in schema["properties"]
    assert any(item.get("type") == "string" for item in schema["properties"]["name"]["anyOf"])
    assert any(
        item.get("type") == "object" for item in schema["properties"]["extra_context"]["anyOf"]
    )


def test_async_method_fields_are_resolved() -> None:
    marshalled = AsyncMarshall(name="Concurrent")
    assert marshalled.model_dump() == {
        "name": "Concurrent",
        "async_details": "Details about Concurrent",
    }
