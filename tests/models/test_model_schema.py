import datetime

import saffier
from saffier.contrib.admin.utils.models import NoCallableDefaultJsonSchema

database = saffier.Database("sqlite:///model-schema.db")
models = saffier.Registry(database=database)


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)
    created = saffier.DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        registry = models


def test_model_json_schema_supports_edgy_style_kwargs() -> None:
    schema = Product.model_json_schema(mode="validation")
    assert schema["title"] == "ProductCreateAdminMarshall"
    assert schema["properties"]["name"]["type"] == "string"
    assert "default" in schema["properties"]["created"]


def test_model_json_schema_can_skip_callable_defaults() -> None:
    schema = Product.model_json_schema(
        schema_generator=NoCallableDefaultJsonSchema,
        mode="validation",
    )

    assert "default" not in schema["properties"]["created"]
