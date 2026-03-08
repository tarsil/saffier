"""Shared helpers for engine adapters.

The helpers in this module keep the per-engine adapters focused on the
differences between libraries while centralizing the Saffier-specific field and
annotation interpretation rules.
"""

from __future__ import annotations

import datetime
import decimal
import ipaddress
import sys
import types
import typing
import uuid
from typing import TYPE_CHECKING, Any, get_args, get_origin

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


def resolve_annotation(annotation: Any, model_class: type[Model]) -> Any:
    """Resolve one possibly-string annotation against a model namespace.

    Args:
        annotation: Annotation object or forward-reference string.
        model_class: Saffier model whose module and namespace should be used for
            evaluation.

    Returns:
        Any: Resolved annotation, or `Any` when the string cannot be evaluated.
    """
    if not isinstance(annotation, str):
        return annotation

    module_name = getattr(model_class, "__module__", "")
    globalns = dict(sys.modules[module_name].__dict__) if module_name in sys.modules else {}
    localns = dict(model_class.__dict__)
    localns.setdefault("typing", typing)
    localns.setdefault("ClassVar", typing.ClassVar)

    try:
        return eval(annotation, globalns, localns)
    except Exception:
        return Any


def annotation_allows_none(annotation: Any) -> bool:
    """Return whether the supplied annotation already accepts `None`.

    Args:
        annotation: Type annotation to inspect.

    Returns:
        bool: `True` when the annotation is already optional.
    """
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return type(None) in get_args(annotation)
    return annotation in (Any, typing.Any, type(None))


def optional_annotation(annotation: Any) -> Any:
    """Wrap an annotation in an optional union when needed.

    Args:
        annotation: Annotation to relax.

    Returns:
        Any: Optionalized annotation.
    """
    if annotation in (Any, typing.Any):
        return Any
    if annotation_allows_none(annotation):
        return annotation
    return annotation | None


def infer_saffier_field_type(field: Any) -> Any:
    """Infer a Python type from one Saffier field validator.

    Args:
        field: Saffier field instance.

    Returns:
        Any: Best-effort Python type for the field.
    """
    if hasattr(field, "target"):
        return Any

    validator_name = field.validator.__class__.__name__
    if validator_name in {"String", "Email", "URL", "Password"}:
        return str
    if validator_name == "UUID":
        return uuid.UUID
    if validator_name == "Integer":
        return int
    if validator_name == "Float":
        return float
    if validator_name == "Decimal":
        return decimal.Decimal
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
    if validator_name == "JSON":
        return dict[str, Any]
    return Any


def saffier_field_annotation(field: Any, model_class: type[Model]) -> Any:
    """Return the effective engine-facing annotation for one Saffier field.

    Args:
        field: Saffier field instance.
        model_class: Model declaring the field.

    Returns:
        Any: Resolved annotation or inferred fallback type.
    """
    annotation = getattr(field, "annotation", None)
    if annotation not in (None, Any):
        return resolve_annotation(annotation, model_class)
    return infer_saffier_field_type(field)


__all__ = [
    "annotation_allows_none",
    "infer_saffier_field_type",
    "optional_annotation",
    "resolve_annotation",
    "saffier_field_annotation",
]
