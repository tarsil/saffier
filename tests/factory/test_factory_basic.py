from types import SimpleNamespace

import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from saffier.testing import FactoryField, ListSubFactory, ModelFactory, SubFactory
from saffier.testing.exceptions import InvalidModelError
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100, null=True)
    language = saffier.CharField(max_length=50, null=True)

    class Meta:
        registry = models


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(ge=1, le=5, default=1)
    user = saffier.ForeignKey(User, null=True)

    class Meta:
        registry = models


def test_factory_exports_are_importable():
    import saffier.testing

    assert "ModelFactory" in saffier.testing.__all__
    assert "SubFactory" in saffier.testing.__all__


def test_factory_requires_model():
    with pytest.raises(InvalidModelError):

        class MissingFactory(ModelFactory):
            class Meta:
                pass

            pass


def test_factory_generates_model_and_defaults():
    class UserFactory(ModelFactory):
        class Meta:
            model = User

        language = FactoryField(callback="language_code")

    user = UserFactory(name="Alice").build()
    assert user.name == "Alice"
    assert user.language is not None
    assert user._db_loaded is True


def test_factory_accepts_model_path_string():
    class ProductFactory(ModelFactory):
        class Meta:
            model = "tests.factory.test_factory_basic.Product"

    product = ProductFactory().build()
    assert product.__class__.__name__ == "Product"


def test_subfactory_and_to_factory_field():
    class ProductFactory(ModelFactory):
        class Meta:
            model = Product

        user = SubFactory(f"{__name__}.ModuleUserFactory")

    product = ProductFactory().build()
    assert product.user is not None
    assert product.user.name == "John Doe"

    class ProductFactory2(ModelFactory):
        class Meta:
            model = Product

        user = ModuleUserFactory().to_factory_field()

    product_2 = ProductFactory2().build()
    assert product_2.user is not None
    assert product_2.user.name == "John Doe"


def test_list_subfactory_and_to_list_factory_field():
    class StaticFactory:
        def build(self, **parameters):
            return {"value": parameters.get("value", "ok")}

    field = ListSubFactory(StaticFactory(), min=2, max=2)
    context = {"faker": SimpleNamespace(random_int=lambda min, max: 2)}
    generated = field._callback(field, context, {"value": "x"})
    assert generated == [{"value": "x"}, {"value": "x"}]

    class UserFactory(ModelFactory):
        class Meta:
            model = User

    list_field = UserFactory().to_list_factory_field(min=2, max=2)
    generated_users = list_field(
        context={"faker": SimpleNamespace(random_int=lambda min, max: 2), "callcounts": {}},
        parameters={},
    )
    assert len(generated_users) == 2
    assert isinstance(generated_users[0], User)


def test_field_callcount_and_parameters():
    class UserFactory(ModelFactory):
        class Meta:
            model = User

        name = FactoryField(
            callback=lambda field, context, parameters: f"user-{field.get_callcount()}",
            parameters={"randomly_unset": False},
        )

    user_1 = UserFactory().build()
    user_2 = UserFactory().build()
    assert user_1.name == "user-1"
    assert user_2.name == "user-2"


def test_factory_mapping_override():
    class ProductFactory(ModelFactory):
        class Meta:
            model = Product
            mappings = {"IntegerField": lambda field, context, params: 5}

    product = ProductFactory().build()
    assert product.rating == 5


def test_factory_build_save_shortcut_without_database():
    class UserFactory(ModelFactory):
        class Meta:
            model = User

    user = UserFactory().build(save=False)
    assert isinstance(user, User)


class ModuleUserFactory(ModelFactory):
    class Meta:
        model = User

    name = "John Doe"
