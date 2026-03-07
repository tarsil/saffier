from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast

from saffier.core.db import fields as saffier_fields
from saffier.core.db.relationships.related import RelatedField

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Model, ReflectModel


class RelationshipCrawlResult(NamedTuple):
    model_class: type[Model] | type[ReflectModel]
    field_name: str
    operator: str | None
    forward_path: str
    reverse_path: str | Literal[False]
    cross_db_remainder: str


def crawl_relationship(
    model_class: type[Model] | type[ReflectModel],
    path: str,
    *,
    traverse_last: bool = False,
) -> RelationshipCrawlResult:
    field_name = path
    reverse_path: str | Literal[False] = ""
    forward_path = ""
    operator: str | None = "exact"
    field: Any = None

    while path:
        splitted = path.split("__", 1)
        field_name = splitted[0]
        field = model_class.fields.get(field_name)
        attr = getattr(model_class, field_name, None)

        if len(splitted) == 2 and isinstance(
            field,
            (
                saffier_fields.ForeignKey,
                saffier_fields.OneToOneField,
                saffier_fields.ManyToManyField,
            ),
        ):
            path = splitted[1]
            model_class = field.target
            reverse_part: str | Literal[False] = cast(
                "str | Literal[False]",
                getattr(field, "related_name", None)
                if getattr(field, "related_name", None) is not False
                else False,
            )
            if reverse_part and reverse_path is not False:
                reverse_path = (
                    f"{reverse_part}__{reverse_path}" if reverse_path else reverse_part
                )
            else:
                reverse_path = False
            forward_path = f"{forward_path}__{field_name}" if forward_path else field_name
            continue

        if len(splitted) == 2 and isinstance(attr, RelatedField):
            path = splitted[1]
            model_class = attr.related_from
            reverse_part = attr.get_foreign_key_field_name()
            if reverse_part and reverse_path is not False:
                reverse_path = (
                    f"{reverse_part}__{reverse_path}" if reverse_path else reverse_part
                )
            else:
                reverse_path = False
            forward_path = f"{forward_path}__{field_name}" if forward_path else field_name
            continue

        if len(splitted) == 2:
            if "__" not in splitted[1]:
                operator = splitted[1]
                break
            raise ValueError(f"Tried to cross field: {field_name!r}, remainder: {splitted[1]!r}")

        operator = "exact"
        break

    if traverse_last:
        attr = getattr(model_class, field_name, None)
        field = model_class.fields.get(field_name)
        if isinstance(
            field,
            (
                saffier_fields.ForeignKey,
                saffier_fields.OneToOneField,
                saffier_fields.ManyToManyField,
            ),
        ):
            model_class = field.target
            reverse_part = cast(
                "str | Literal[False]",
                getattr(field, "related_name", None)
                if getattr(field, "related_name", None) is not False
                else False,
            )
        elif isinstance(attr, RelatedField):
            model_class = attr.related_from
            reverse_part = attr.get_foreign_key_field_name()
        else:
            reverse_part = field_name
        if reverse_part and reverse_path is not False:
            reverse_path = f"{reverse_part}__{reverse_path}" if reverse_path else reverse_part
        else:
            reverse_path = False
    elif reverse_path is not False:
        reverse_path = f"{field_name}__{reverse_path}" if reverse_path else field_name

    return RelationshipCrawlResult(
        model_class=model_class,
        field_name=field_name,
        operator=operator,
        forward_path=forward_path,
        reverse_path=reverse_path,
        cross_db_remainder="",
    )
