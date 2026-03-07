from __future__ import annotations

import copy
import datetime
import decimal
import ipaddress
import sys
import typing
import uuid
from dataclasses import dataclass
from typing import Any, get_origin

from saffier.conf.module_import import import_string
from saffier.core.marshalls.config import ConfigMarshall
from saffier.core.marshalls.fields import BaseMarshallField
from saffier.core.utils.functional import extract_field_annotations_and_defaults
from saffier.exceptions import MarshallFieldDefinitionError

if typing.TYPE_CHECKING:
    from saffier.core.db.fields.base import Field
    from saffier.core.db.models.model import Model
    from saffier.core.marshalls.base import Marshall


def _make_pk_field_read_only(field: Field) -> Field:
    if not getattr(field, "primary_key", False):
        return field
    field = copy.copy(field)
    field.validator.read_only = True
    return field


@dataclass(slots=True)
class MarshallFieldBinding:
    name: str
    field_type: Any
    exclude: bool = False
    required: bool = False
    null: bool = False
    default: Any = None
    has_default: bool = False
    callable_default: bool = False
    read_only: bool = False
    source: str | None = None
    is_method: bool = False
    model_field: Field | None = None
    marshall_field: BaseMarshallField | None = None

    def get_default_value(self) -> Any:
        if not self.has_default:
            return None
        if callable(self.default):
            return self.default()
        return self.default


def _build_model_binding(name: str, field: Field) -> MarshallFieldBinding:
    annotation = getattr(field, "annotation", None)
    if annotation in (None, Any):
        annotation = _infer_field_type(field)
    validator = field.validator
    default = getattr(validator, "default", None)
    return MarshallFieldBinding(
        name=name,
        field_type=annotation,
        exclude=False,
        required=not field.null and not validator.has_default() and not validator.read_only,
        null=field.null,
        default=default if validator.has_default() else None,
        has_default=validator.has_default(),
        callable_default=callable(default) if validator.has_default() else False,
        read_only=bool(validator.read_only),
        source=name,
        is_method=False,
        model_field=field,
    )


def _infer_field_type(field: Field) -> Any:
    validator_name = field.validator.__class__.__name__
    if validator_name in {"String", "Email", "URL", "Password"}:
        return str
    if validator_name == "UUID":
        return uuid.UUID
    if validator_name in {"Integer"}:
        return int
    if validator_name in {"Float", "Decimal"}:
        return decimal.Decimal if validator_name == "Decimal" else float
    if validator_name == "Boolean":
        return bool
    if validator_name == "Binary":
        return bytes
    if validator_name == "Date":
        return datetime.date
    if validator_name == "Time":
        return datetime.time
    if validator_name == "DateTime":
        return datetime.datetime
    if validator_name == "Duration":
        return datetime.timedelta
    if validator_name == "IPAddress":
        return ipaddress.IPv4Address
    return Any


def _build_declared_binding(
    name: str,
    field: BaseMarshallField,
    model_field: Field | None,
) -> MarshallFieldBinding:
    default = getattr(field, "default", None)
    return MarshallFieldBinding(
        name=name,
        field_type=field.field_type,
        exclude=field.exclude,
        required=field.is_required(),
        null=field.null,
        default=default if field.has_default() else None,
        has_default=field.has_default(),
        callable_default=callable(default) if field.has_default() else False,
        read_only=False,
        source=field.source,
        is_method=field.__is_method__,
        model_field=model_field,
        marshall_field=field,
    )


def _resolve_annotation(annotation: Any, attrs: dict[str, Any]) -> Any:
    if not isinstance(annotation, str):
        return annotation

    module_name = attrs.get("__module__")
    globalns = dict(sys.modules[module_name].__dict__) if module_name in sys.modules else {}
    localns = dict(attrs)
    localns.setdefault("typing", typing)
    localns.setdefault("ClassVar", typing.ClassVar)

    try:
        return eval(annotation, globalns, localns)
    except Exception:
        return annotation


class MarshallMeta(type):
    __slots__ = ()

    def __new__(cls, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> Any:
        annotations = dict(attrs.get("__annotations__", {}))
        marshall_config = attrs.get("marshall_config")
        attrs, declared_fields = extract_field_annotations_and_defaults(attrs, BaseMarshallField)
        has_parents = any(isinstance(parent, MarshallMeta) for parent in bases)

        marshall_class: type[Marshall] = super().__new__(cls, name, bases, attrs)

        if not has_parents:
            marshall_class.marshall_config = {}
            marshall_class.model_fields = {}
            marshall_class.__custom_fields__ = {}
            marshall_class.__local_fields__ = {}
            marshall_class.__incomplete_fields__ = ()
            marshall_class.__lazy__ = False
            return marshall_class

        if marshall_config is None:
            raise MarshallFieldDefinitionError(
                "The 'marshall_config' was not found. Make sure it is declared and set."
            )

        marshall_config_annotation = _resolve_annotation(annotations.get("marshall_config"), attrs)
        if (
            marshall_config_annotation is not None
            and get_origin(marshall_config_annotation) is not typing.ClassVar
        ):
            raise MarshallFieldDefinitionError(
                f"'marshall_config' is part of the fields of '{name}'. Did you forget to annotate with 'ClassVar'?"
            )

        model_ref = marshall_config.get("model")
        assert model_ref is not None, "'model' must be declared in the 'ConfigMarshall'."
        model: type[Model]
        if isinstance(model_ref, str):
            model = import_string(model_ref)
            marshall_config["model"] = model
        else:
            model = model_ref

        base_fields_include = marshall_config.get("fields")
        base_fields_exclude = marshall_config.get("exclude")

        assert base_fields_include is None or base_fields_exclude is None, (
            "Use either 'fields' or 'exclude', not both."
        )
        assert base_fields_include is not None or base_fields_exclude is not None, (
            "Either 'fields' or 'exclude' must be declared."
        )

        show_pk = False
        if base_fields_exclude is not None:
            selected_model_fields = {
                key: value for key, value in model.fields.items() if key not in base_fields_exclude
            }
        elif "__all__" in typing.cast(list[str], base_fields_include):
            selected_model_fields = dict(model.fields)
            show_pk = True
        else:
            selected_model_fields = {
                key: value
                for key, value in model.fields.items()
                if key in typing.cast(list[str], base_fields_include)
            }

        if marshall_config.get("exclude_autoincrement", False):
            selected_model_fields = {
                key: value
                for key, value in selected_model_fields.items()
                if not getattr(value, "autoincrement", False)
            }

        if marshall_config.get("primary_key_read_only", False):
            selected_model_fields = {
                key: _make_pk_field_read_only(value)
                for key, value in selected_model_fields.items()
            }

        if marshall_config.get("exclude_read_only", False):
            selected_model_fields = {
                key: value
                for key, value in selected_model_fields.items()
                if not value.validator.read_only
            }

        model_bindings = {
            key: _build_model_binding(key, value) for key, value in selected_model_fields.items()
        }

        local_fields: dict[str, BaseMarshallField] = {}
        custom_fields: dict[str, BaseMarshallField] = {}
        for field_name, field in declared_fields.items():
            source_model_field = selected_model_fields.get(field_name) or model.fields.get(
                field_name
            )
            model_bindings[field_name] = _build_declared_binding(
                field_name, field, source_model_field
            )
            if field.__is_method__ or (
                field.source is not None and field_name not in model.fields
            ):
                custom_fields[field_name] = field
            elif field_name not in model.fields and field.source is None:
                local_fields[field_name] = field

        for field_name, field in custom_fields.items():
            if field.__is_method__ and not hasattr(marshall_class, f"get_{field_name}"):
                raise MarshallFieldDefinitionError(
                    f"Field '{field_name}' declared but no 'get_{field_name}' found in '{name}'."
                )

        required_fields = {
            field_name
            for field_name, field in model.fields.items()
            if not field.null
            and not field.validator.has_default()
            and not field.validator.read_only
        }

        marshall_class.__show_pk__ = show_pk
        marshall_class.marshall_config = typing.cast(ConfigMarshall, marshall_config)
        marshall_class.model_fields = model_bindings
        marshall_class.__custom_fields__ = custom_fields
        marshall_class.__local_fields__ = local_fields
        marshall_class.__incomplete_fields__ = tuple(
            sorted(
                field_name for field_name in required_fields if field_name not in model_bindings
            )
        )
        marshall_class.__lazy__ = bool(marshall_class.__incomplete_fields__)
        return marshall_class


__all__ = ["MarshallFieldBinding", "MarshallMeta"]
