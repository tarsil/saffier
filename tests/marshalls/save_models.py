from __future__ import annotations

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100, null=True)
    email = saffier.EmailField(max_length=100, null=True)
    language = saffier.CharField(max_length=200, null=True)
    description = saffier.TextField(max_length=5000, null=True)

    class Meta:
        registry = models


class SpecialUser(saffier.Model):
    special_id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, null=True)

    class Meta:
        registry = models
