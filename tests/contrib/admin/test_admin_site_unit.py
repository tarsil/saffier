from __future__ import annotations

from base64 import urlsafe_b64encode
from types import SimpleNamespace
from typing import Any

import orjson
import pytest

import saffier
from saffier.contrib.admin import AdminSite
from saffier.contrib.admin.exceptions import AdminValidationError


class _FakeFormData:
    def __init__(self, editor_data: Any = None):
        self._editor_data = editor_data

    def get(self, key: str) -> Any:
        if key == "editor_data":
            return self._editor_data
        return None

    def multi_items(self):
        return []


def _model(*, abstract: bool = False) -> type[Any]:
    return type("Model", (), {"meta": SimpleNamespace(abstract=abstract)})


def _registry(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        models=kwargs.get("models", {}),
        reflected=kwargs.get("reflected", {}),
        pattern_models=kwargs.get("pattern_models", set()),
    )


def test_admin_site_registered_models_respect_filters():
    registry = _registry(
        models={
            "PatternModel": _model(),
            "AbstractModel": _model(abstract=True),
            "Included": _model(),
            "Excluded": _model(),
        },
        reflected={"Reflected": _model(), "RefExcluded": _model()},
        pattern_models={"PatternModel"},
    )
    site = AdminSite(
        registry=registry,
        include_models={"Included", "Excluded", "Reflected", "RefExcluded"},
        exclude_models={"Excluded", "RefExcluded"},
    )
    assert list(site.get_registered_models().keys()) == ["Included", "Reflected"]


@pytest.mark.anyio
async def test_admin_site_model_counts_handle_query_errors():
    class SuccessQuery:
        async def count(self) -> int:
            return 7

    class FailingQuery:
        async def count(self) -> int:
            raise RuntimeError("boom")

    success_model = type(
        "SuccessModel",
        (),
        {"meta": SimpleNamespace(abstract=False), "__name__": "Success", "query": SuccessQuery()},
    )
    failing_model = type(
        "FailingModel",
        (),
        {"meta": SimpleNamespace(abstract=False), "__name__": "Failing", "query": FailingQuery()},
    )

    site = AdminSite(
        registry=_registry(models={"Success": success_model, "Failing": failing_model})
    )
    counts = await site.get_model_counts()
    assert counts == [
        {"name": "Failing", "verbose": "FailingModel", "count": 0},
        {"name": "Success", "verbose": "SuccessModel", "count": 7},
    ]


def test_admin_site_field_schema_and_pk_parsing_errors():
    readonly = saffier.CharField(max_length=50, null=True)
    readonly.validator.read_only = True

    model = type(
        "Entry",
        (),
        {
            "meta": SimpleNamespace(abstract=False),
            "pkname": "id",
            "fields": {
                "id": saffier.IntegerField(primary_key=True, autoincrement=True),
                "readonly": readonly,
                "tags": saffier.ManyToManyField("Tag"),
                "title": saffier.CharField(max_length=50, null=True),
            },
        },
    )

    site = AdminSite(registry=_registry(models={"Entry": model}))
    write_fields = site.get_model_fields("Entry", for_write=True)
    assert [field["name"] for field in write_fields] == ["title"]

    encoded_non_dict = urlsafe_b64encode(orjson.dumps([1, 2, 3])).decode()
    with pytest.raises(AdminValidationError):
        site.parse_object_pk(encoded_non_dict)


def test_admin_site_search_and_form_payload_errors():
    numeric_only_model = type(
        "NumericOnly",
        (),
        {"fields": {"amount": saffier.IntegerField(null=True)}, "pkname": "id"},
    )
    site = AdminSite(registry=_registry(models={"NumericOnly": numeric_only_model}))
    assert site._build_search_clause(numeric_only_model, "search") is None

    with pytest.raises(AdminValidationError):
        site.form_to_payload(_FakeFormData(editor_data=orjson.dumps([1, 2]).decode()))


def test_admin_site_handles_composite_primary_keys():
    model = type(
        "CompositeEntry",
        (),
        {
            "meta": SimpleNamespace(abstract=False),
            "pkname": "id",
            "pknames": ("id", "slug"),
            "fields": {
                "id": saffier.IntegerField(primary_key=True),
                "slug": saffier.CharField(max_length=50, primary_key=True),
            },
        },
    )
    instance = type(
        "CompositeInstance",
        (),
        {
            "pkname": "id",
            "pk": {"id": 1, "slug": "entry"},
            "id": 1,
            "slug": "entry",
        },
    )()

    site = AdminSite(registry=_registry(models={"CompositeEntry": model}))
    schema = site.get_model_schema("CompositeEntry")

    assert schema["pk_names"] == ["id", "slug"]
    encoded = site.create_object_pk(instance)
    assert site.parse_object_pk(encoded) == {"id": 1, "slug": "entry"}


def test_admin_site_payload_coercion_branches():
    readonly = saffier.CharField(max_length=50)
    readonly.validator.read_only = True

    defaults_model = type(
        "DefaultsModel",
        (),
        {
            "fields": {
                "id": saffier.IntegerField(primary_key=True, autoincrement=True),
                "tags": saffier.ManyToManyField("Tag"),
                "readonly": readonly,
                "optional": saffier.CharField(max_length=50, null=True),
                "named": saffier.CharField(max_length=50, default="default-name"),
            },
        },
    )

    site = AdminSite(registry=_registry(models={"DefaultsModel": defaults_model}))
    values = site._coerce_payload(defaults_model, {})
    assert values["optional"] is None
    assert values["named"] == "default-name"
    assert "tags" not in values
    assert "readonly" not in values

    partial_values = site._coerce_payload(
        defaults_model,
        {"tags": ["x"], "readonly": "ignored", "named": "provided"},
        partial=True,
    )
    assert partial_values == {"named": "provided"}

    error_model = type(
        "ErrorModel",
        (),
        {"fields": {"age": saffier.IntegerField(null=False)}},
    )
    with pytest.raises(AdminValidationError) as exc:
        site._coerce_payload(
            error_model,
            {"age": "invalid"},
            partial=True,
        )
    assert "age" in exc.value.errors
