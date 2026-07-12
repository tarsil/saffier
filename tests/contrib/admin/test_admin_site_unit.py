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
    """Form-data stand-in for AdminSite payload coercion tests.

    The admin site receives Lilya form data during create and edit requests.
    This tiny object supplies only the methods that ``form_to_payload`` reads,
    keeping unit coverage focused on JSONEditor payload parsing.
    """

    def __init__(self, editor_data: Any = None):
        """Store optional serialized JSONEditor data for later lookup.

        Args:
            editor_data: Value returned when the admin site asks for the
                ``editor_data`` form field.
        """
        self._editor_data = editor_data

    def get(self, key: str) -> Any:
        """Return the requested form field value.

        Args:
            key: Form field name requested by ``AdminSite``.

        Returns:
            Any: Stored editor data for ``editor_data`` or ``None`` for every
            other key.
        """
        if key == "editor_data":
            return self._editor_data
        return None

    def multi_items(self):
        """Return an empty multi-value iterator for non-JSON form branches.

        The current unit tests exercise JSONEditor-backed forms, so no ordinary
        field/value pairs are needed.
        """
        return []


def _model(*, abstract: bool = False) -> type[Any]:
    """Create a lightweight model-like class for registry filtering tests.

    Args:
        abstract: Whether the fake model should be treated as abstract by
            ``AdminSite.get_registered_models``.

    Returns:
        type[Any]: Dynamically created class with a minimal ``meta`` object.
    """
    return type("Model", (), {"meta": SimpleNamespace(abstract=abstract)})


def _registry(**kwargs: Any) -> SimpleNamespace:
    """Create a minimal registry-like object for AdminSite unit tests.

    Args:
        **kwargs: Optional ``models``, ``reflected``, and ``pattern_models``
            values used to shape the fake registry.

    Returns:
        SimpleNamespace: Object exposing the registry attributes read by
        ``AdminSite``.
    """
    return SimpleNamespace(
        models=kwargs.get("models", {}),
        reflected=kwargs.get("reflected", {}),
        pattern_models=kwargs.get("pattern_models", set()),
    )


def test_admin_site_registered_models_respect_filters():
    """Verify model discovery honors abstract, reflected, include, and exclude rules.

    ``AdminSite`` builds its sidebar and dashboard from registry state. This
    test makes sure pattern-generated and abstract models are hidden, explicit
    include filters are respected, and exclude filters win over inclusion.
    """
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
    """Verify dashboard counts degrade gracefully when model queries fail.

    Admin pages should still render when one model raises during ``count``. The
    failing model reports zero while successful models keep their real count and
    admin creation metadata.
    """

    class SuccessQuery:
        """Query stand-in that returns a successful object count.

        The fake model exposes this object as ``query`` so the admin service can
        call the same asynchronous ``count`` API used by real querysets.
        """

        async def count(self) -> int:
            """Return a deterministic count for the success branch.

            Returns:
                int: Count value surfaced in the dashboard model summary.
            """
            return 7

    class FailingQuery:
        """Query stand-in that raises during dashboard counting.

        The failure branch proves the admin dashboard does not break when a
        model is temporarily unavailable or its count query fails.
        """

        async def count(self) -> int:
            """Raise a deterministic error for the failure branch.

            Raises:
                RuntimeError: Always raised to simulate a broken count query.
            """
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
        {"name": "Failing", "verbose": "FailingModel", "count": 0, "no_admin_create": False},
        {"name": "Success", "verbose": "SuccessModel", "count": 7, "no_admin_create": False},
    ]


def test_admin_site_field_schema_and_pk_parsing_errors():
    """Verify writable field schema filtering and primary-key validation.

    Read-only, relation, and auto-increment primary-key fields should be absent
    from write schemas. The same test covers malformed encoded primary-key
    payloads so object routes can reject invalid IDs cleanly.
    """
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
    """Verify search and form parsing error branches.

    Numeric-only models should not generate text search expressions, and
    JSONEditor payloads must deserialize to objects rather than arbitrary JSON
    arrays.
    """
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
    """Verify schema and URL encoding behavior for composite primary keys.

    Composite primary-key models need stable object URLs and reversible primary
    key parsing. This test proves the admin service advertises every primary key
    column and round-trips encoded object identifiers.
    """
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
    """Verify admin payload coercion skips and validates expected field types.

    The coercion helper should omit many-to-many and read-only fields, fill
    nullable/default values on full creates, preserve partial update semantics,
    and surface validation errors per field.
    """
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
