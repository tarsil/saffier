import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class BaseUser(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, null=True)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        abstract = True


class User(BaseUser):
    class Meta:
        registry = models
        tablename = "lazy_users"


class Product(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, null=True)
    rating = saffier.IntegerField(minimum=1, maximum=5, default=1)
    in_stock = saffier.BooleanField(default=False)

    class Meta:
        registry = models
        tablename = "lazy_products"


def test_control_lazyness():
    assert User.meta is models.get_model("User").meta
    assert not BaseUser.meta._fields_are_initialized
    assert not BaseUser.meta._field_stats_are_initialized
    assert not User.meta._fields_are_initialized
    assert User.meta._field_stats_are_initialized
    assert "name" not in User.meta.columns_to_field.data
    assert User.meta._fields_are_initialized
    assert not Product.meta._fields_are_initialized
    assert "rating" not in Product.meta.columns_to_field.data
    assert Product.meta._fields_are_initialized

    assert "id" not in Product.meta.columns_to_field.data
    assert "id" in User.meta.get_columns_for_name("id")[0].key
    User.meta.columns_to_field.init()
    assert "id" in User.meta.columns_to_field.data

    models.invalidate_models()
    assert User.meta is models.get_model("User").meta
    assert not User.meta._fields_are_initialized
    assert "name" not in User.meta.columns_to_field.data
    assert not Product.meta._fields_are_initialized
    assert "rating" not in Product.meta.columns_to_field.data

    models.init_models(init_column_mappers=False, init_class_attrs=False)
    assert "name" not in User.meta.columns_to_field.data
    assert "rating" not in Product.meta.columns_to_field.data
    assert "pknames" not in Product.__dict__
    models.init_models()
    assert "name" in User.meta.columns_to_field.data
    assert "rating" in Product.meta.columns_to_field.data
