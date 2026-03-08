from __future__ import annotations

from typing import Any


def get_model_fields(attrs: dict[Any, Any], base_type: type) -> dict[Any, Any]:
    return {key: value for key, value in attrs.items() if isinstance(value, base_type)}


def extract_field_annotations_and_defaults(
    attrs: dict[Any, Any],
    base_type: type,
) -> tuple[dict[Any, Any], dict[Any, Any]]:
    attrs, model_fields = populate_field_annotations_and_defaults(attrs, base_type)
    return attrs, model_fields


def populate_field_annotations_and_defaults(
    attrs: dict[Any, Any],
    base_type: type,
) -> tuple[dict[Any, Any], dict[Any, Any]]:
    model_fields = {}
    potential_fields = get_model_fields(attrs, base_type)

    for field_name, field in potential_fields.items():
        field.name = field_name
        model_fields[field_name] = field

    return attrs, model_fields


__all__ = [
    "extract_field_annotations_and_defaults",
    "get_model_fields",
    "populate_field_annotations_and_defaults",
]
