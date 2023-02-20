import datetime
import decimal
import ipaddress
import random
import string
import uuid
from enum import Enum

import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import fields
from saffier.db.connection import Database
from saffier.db.datastructures import Index

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str


def test_raises_value_error_on_wrong_max_length():
    with pytest.raises(ValueError) as raised:

        class User(saffier.Model):
            name = saffier.CharField(max_length=255)
            title = saffier.CharField(max_length=255)

            class Meta:
                registry = models
                indexes = [Index(fields=["name", "title"], name=get_random_string(31))]


def test_raises_value_error_on_wrong_type_passed_fields():
    with pytest.raises(ValueError) as raised:

        class User(saffier.Model):
            name = saffier.CharField(max_length=255)
            title = saffier.CharField(max_length=255)

            class Meta:
                registry = models
                indexes = [Index(fields=2)]


def test_raises_value_error_on_wrong_type_passed_inside_fields_list():
    with pytest.raises(ValueError) as raised:

        class User(saffier.Model):
            name = saffier.CharField(max_length=255)
            title = saffier.CharField(max_length=255)

            class Meta:
                registry = models
                indexes = [Index(fields=["name", 2])]
