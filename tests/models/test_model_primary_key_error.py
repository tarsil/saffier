from enum import Enum

import pytest

import saffier
from saffier import Registry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = Registry(database=database)
nother = Registry(database=database)

pytestmark = pytest.mark.anyio


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


@pytest.mark.parametrize(
    "field,max_length,max_digits,decimal_places",
    [
        (saffier.BooleanField, None, None, None),
        (saffier.CharField, 255, None, None),
        (saffier.UUIDField, None, None, None),
        (saffier.TextField, None, None, None),
        (saffier.DateField, None, None, None),
        (saffier.DateTimeField, None, None, None),
        (saffier.FloatField, None, None, None),
        (saffier.DecimalField, None, 5, 2),
        (saffier.TimeField, None, None, None),
        (saffier.ChoiceField, None, None, None),
    ],
    ids=[
        "BooleanField",
        "CharField",
        "UUIDField",
        "TextField",
        "DateField",
        "DateTimeField",
        "FloatField",
        "DecimalField",
        "TimeField",
        "ChoiceField",
    ],
)
async def test_model_custom_primary_key_raised_error_without_default(
    field, max_length, max_digits, decimal_places
):
    with pytest.raises(ValueError) as raised:
        kwargs = {
            "max_length": max_length,
            "max_digits": max_digits,
            "decimal_places": decimal_places,
            "choices": StatusEnum,
        }

        class Profile(saffier.Model):
            id = field(primary_key=True, **kwargs)
            language = saffier.CharField(max_length=200, null=True)
            age = saffier.IntegerField()

            class Meta:
                registry = models

    assert (
        raised.value.args[0]
        == "Primary keys other then IntegerField and BigIntegerField, must provide a default."
    )
