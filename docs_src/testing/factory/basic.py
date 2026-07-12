import saffier
from saffier.testing import FactoryField, ModelFactory

database = saffier.Database("sqlite+aiosqlite:///factory-docs.sqlite")
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=8, null=True)

    class Meta:
        registry = models


class UserFactory(ModelFactory):
    class Meta:
        model = User

    language = FactoryField(callback="language_code")


user = UserFactory(name="Ada").build()

assert user.name == "Ada"
assert user.language
