import copy

import pytest
from pydantic import ValidationError as PydanticValidationError

import saffier
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
plain_models = saffier.Registry(database=database)
dummy_models = saffier.Registry(database=database, model_engine="dummy-test")


class DummyEngine(saffier.ModelEngine):
    name = "dummy-test"

    def get_model_class(self, model_class, *, mode: str = "projection"):
        del model_class, mode
        return dict

    def validate_model(self, model_class, value, *, mode: str = "validation"):
        del model_class, mode
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "model_dump"):
            return value.model_dump()
        raise TypeError("Dummy engine only accepts mapping-like values.")

    def to_saffier_data(self, model_class, value, *, exclude_unset: bool = False):
        del model_class, exclude_unset
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "model_dump"):
            return value.model_dump()
        raise TypeError("Dummy engine only accepts mapping-like values.")

    def json_schema(self, model_class, *, mode: str = "projection", **kwargs):
        del kwargs
        return {"title": f"{model_class.__name__}{mode.title()}DummyEngine"}


saffier.register_model_engine("dummy-test", DummyEngine, overwrite=True)


class PlainWidget(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = plain_models


class DummyWidget(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = dummy_models


class DisabledWidget(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = dummy_models
        model_engine = False


class PydanticWidget(saffier.Model):
    name = saffier.CharField(max_length=100)
    quantity = saffier.IntegerField(default=1)

    class Meta:
        registry = dummy_models
        model_engine = "pydantic"


class EngineBase(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        abstract = True
        registry = dummy_models
        model_engine = "pydantic"


class EngineChild(EngineBase):
    rating = saffier.IntegerField(default=0)

    class Meta:
        registry = dummy_models


class UnknownEngineWidget(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = plain_models
        model_engine = "does-not-exist"


def test_default_mode_keeps_core_behavior_unchanged() -> None:
    widget = PlainWidget(name="plain")

    assert PlainWidget.get_model_engine() is None
    assert widget.model_dump() == {"name": "plain"}

    with pytest.raises(ImproperlyConfigured, match="no model engine configured"):
        widget.to_engine_model()


def test_engine_registration_and_registry_selection() -> None:
    widget = DummyWidget(name="dummy")

    assert DummyWidget.get_model_engine_name() == "dummy-test"
    assert DummyWidget.get_engine_model_class() is dict
    assert widget.engine_dump() == {"name": "dummy"}
    assert DummyWidget.engine_json_schema() == {"title": "DummyWidgetProjectionDummyEngine"}


def test_per_model_override_and_opt_out() -> None:
    assert DisabledWidget.get_model_engine() is None
    assert PydanticWidget.get_model_engine_name() == "pydantic"
    assert PydanticWidget.get_model_engine() is saffier.get_model_engine("pydantic")


def test_engine_configuration_is_inherited_by_child_and_proxy_model() -> None:
    child = EngineChild(name="child", rating=5)

    assert EngineChild.get_model_engine_name() == "pydantic"
    assert EngineChild.proxy_model.get_model_engine_name() == "pydantic"
    assert child.engine_dump() == {"name": "child", "rating": 5}


def test_pydantic_engine_projection_validation_and_roundtrip() -> None:
    widget = PydanticWidget(name="apples", quantity=3)

    projected = widget.to_engine_model()
    validated = PydanticWidget.engine_validate({"name": "pears", "quantity": "7"})
    rebuilt = PydanticWidget.from_engine(validated)

    assert projected.model_dump(exclude_unset=True) == {"name": "apples", "quantity": 3}
    assert widget.engine_dump() == {"name": "apples", "quantity": 3}
    assert '"name":"apples"' in widget.engine_dump_json()
    assert validated.name == "pears"
    assert validated.quantity == 7
    assert isinstance(rebuilt, PydanticWidget)
    assert rebuilt.model_dump() == {"name": "pears", "quantity": 7}


def test_pydantic_engine_exposes_validation_schema() -> None:
    schema = PydanticWidget.engine_json_schema(mode="validation")

    assert schema["title"] == "PydanticWidgetValidationEngineModel"
    assert "name" in schema["properties"]
    assert "quantity" in schema["properties"]


def test_pydantic_engine_reports_validation_errors() -> None:
    with pytest.raises(PydanticValidationError):
        PydanticWidget.engine_validate({"name": "bad", "quantity": "wrong"})


def test_unknown_engine_name_raises_when_resolved() -> None:
    with pytest.raises(ImproperlyConfigured, match="does-not-exist"):
        UnknownEngineWidget.get_model_engine()


def test_duplicate_registration_requires_overwrite() -> None:
    saffier.register_model_engine("duplicate-test", DummyEngine(), overwrite=True)

    with pytest.raises(ImproperlyConfigured, match="duplicate-test"):
        saffier.register_model_engine("duplicate-test", DummyEngine())


def test_registry_copy_preserves_model_engine_configuration() -> None:
    copied_registry = copy.copy(dummy_models)
    copied_model = copied_registry.models["DummyWidget"]

    assert copied_registry.model_engine == "dummy-test"
    assert copied_model.get_model_engine_name() == "dummy-test"
