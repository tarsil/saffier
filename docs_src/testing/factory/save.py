import anyio

import saffier
from saffier.testing import ModelFactory

database = saffier.Database("sqlite+aiosqlite:///factory-docs.sqlite")
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class UserFactory(ModelFactory):
    class Meta:
        model = User

    name = "Ada"


async def main() -> None:
    await models.create_all()
    try:
        async with database:
            user = await UserFactory().build_and_save()
            assert user.pk is not None
    finally:
        await models.drop_all()


if __name__ == "__main__":
    anyio.run(main)
