from contextlib import asynccontextmanager

import pytest
from monkay import Monkay

import saffier
from saffier.contrib.permissions import BasePermission
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=database)


class PermissionExtension:
    name = "permissions-test"

    def apply(self, value: Monkay) -> None:
        class User(saffier.StrictModel):
            name = saffier.CharField(max_length=100, unique=True)

            class Meta:
                registry = value.instance.registry

        class Permission(BasePermission):
            users = saffier.ManyToMany("User", through_tablename=saffier.NEW_M2M_NAMING)

            class Meta:
                registry = value.instance.registry
                unique_together = [("name",)]


@asynccontextmanager
async def create_test_database():
    async with database:
        await models.create_all()
        async with models:
            yield
        if not database.drop:
            await models.drop_all()
        models.models.clear()
        reflected = getattr(models, "reflected", None)
        if isinstance(reflected, dict):
            reflected.clear()


async def test_extensions_add_extension():
    with saffier.monkay.with_extensions({}) as extensions:
        saffier.monkay.add_extension(PermissionExtension)
        assert "permissions-test" in extensions
        with saffier.monkay.with_instance(saffier.Instance(models), apply_extensions=True):
            async with create_test_database():
                User = models.get_model("User")
                Permission = models.get_model("Permission")
                user = await User.query.create(name="edgy")
                permission = await Permission.query.create(users=[user], name="view")
                assert await Permission.query.users("view").get() == user
                assert await Permission.query.users("edit").count() == 0
                assert await Permission.query.permissions_of(user).get() == permission


async def test_extensions_extension_settings():
    with (
        saffier.monkay.with_settings(
            saffier.monkay.settings.model_copy(update={"extensions": [PermissionExtension]})
        ),
        saffier.monkay.with_extensions({}) as extensions,
    ):
        assert "permissions-test" not in extensions
        saffier.monkay.evaluate_settings(on_conflict="error")
        assert "permissions-test" in extensions
        with saffier.monkay.with_instance(saffier.Instance(models), apply_extensions=True):
            async with create_test_database():
                User = models.get_model("User")
                Permission = models.get_model("Permission")
                user = await User.query.create(name="edgy")
                permission = await Permission.query.create(users=[user], name="view")
                assert await Permission.query.users("view").get() == user
                assert await Permission.query.users("edit").count() == 0
                assert await Permission.query.permissions_of(user).get() == permission
