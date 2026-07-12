from types import SimpleNamespace

import saffier
from saffier.testing import ListSubFactory, ModelFactory, SubFactory

database = saffier.Database("sqlite+aiosqlite:///factory-docs.sqlite")
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Team(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    owner = saffier.ForeignKey(User)

    class Meta:
        registry = models


class UserFactory(ModelFactory):
    class Meta:
        model = User

    name = "Ada"


class TeamFactory(ModelFactory):
    class Meta:
        model = Team

    owner = SubFactory(UserFactory())


team = TeamFactory(name="Research").build()
members = ListSubFactory(UserFactory(), min=2, max=2)(
    context={
        "faker": SimpleNamespace(random_int=lambda min, max: 2),
        "callcounts": {},
    },
    parameters={},
)

assert team.owner.name == "Ada"
assert len(members) == 2
