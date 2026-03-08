import pytest

import saffier
from saffier.exceptions import ValidationError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class LooseProduct(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Product(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5, default=1)

    class Meta:
        registry = models


def test_strict_model_is_exported() -> None:
    assert issubclass(Product, saffier.StrictModel)


def test_strict_model_validates_init() -> None:
    with pytest.raises(ValidationError):
        Product(name="Widget", rating="bad")


def test_strict_model_validates_assignment() -> None:
    product = Product(name="Widget", rating=1)

    with pytest.raises(ValidationError):
        product.rating = "bad"

    product.rating = 4
    assert product.rating == 4


def test_strict_model_rejects_unknown_public_attributes() -> None:
    product = Product(name="Widget", rating=1)

    with pytest.raises(AttributeError):
        product.extra = "forbidden"


def test_regular_model_still_allows_runtime_attributes() -> None:
    product = LooseProduct(name="Loose")
    product.extra = "allowed"

    assert product.extra == "allowed"
