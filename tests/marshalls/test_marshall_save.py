from __future__ import annotations

from typing import ClassVar

import pytest

import saffier
from tests.marshalls.save_models import SpecialUser, User, database, models

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["__all__"],
    )


class ImportedUserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model="tests.marshalls.save_models.User",
        fields=["__all__"],
    )


class SpecialUserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=SpecialUser,
        fields=["name"],
    )


async def test_marshall_save_creates_a_model() -> None:
    marshalled = UserMarshall(
        name="Saffier",
        email="saffier@ravyn.dev",
        language="EN",
        description="Created from marshall",
    )

    await marshalled.save()

    saved = await User.query.get(name="Saffier")
    assert saved.email == "saffier@ravyn.dev"
    assert marshalled.model_dump() == {
        "id": 1,
        "name": "Saffier",
        "email": "saffier@ravyn.dev",
        "language": "EN",
        "description": "Created from marshall",
    }


async def test_marshall_save_updates_existing_instance() -> None:
    user = await User.query.create(
        name="Original",
        email="original@ravyn.dev",
        language="PT",
        description="Before update",
    )
    marshalled = UserMarshall(instance=user)

    marshalled.name = "Updated"
    marshalled.language = "EN"
    await marshalled.save()

    updated = await User.query.get(pk=user.pk)
    assert updated.name == "Updated"
    assert updated.language == "EN"
    assert updated.email == "original@ravyn.dev"


async def test_marshall_import_string_model_resolution() -> None:
    marshalled = ImportedUserMarshall(name="Imported")
    await marshalled.save()

    saved = await User.query.get(name="Imported")
    assert saved.pk == marshalled.instance.pk
    assert marshalled.model_dump()["id"] == saved.pk


async def test_marshall_with_explicit_non_standard_primary_key() -> None:
    marshalled = SpecialUserMarshall(name="Custom PK")
    await marshalled.save()

    saved = await SpecialUser.query.get(name="Custom PK")
    assert saved.special_id == marshalled.instance.special_id
    assert marshalled.model_dump() == {"name": "Custom PK"}
