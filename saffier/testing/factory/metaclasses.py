from __future__ import annotations

from inspect import getmro, isclass
from typing import TYPE_CHECKING, Any, Literal, cast

from saffier.core.db.models import Model
from saffier.core.terminal import Print
from saffier.exceptions import ValidationError
from saffier.testing.exceptions import InvalidModelError
from saffier.utils.compat import is_class_and_subclass

from .faker import make_faker
from .fields import FactoryField
from .mappings import DEFAULT_MAPPING

if TYPE_CHECKING:
    from .base import ModelFactory
    from .types import FactoryCallback

terminal = Print()


class MetaInfo:
    __slots__ = ("model", "fields", "faker", "mappings", "callcounts")
    model: type[Model]
    mappings: dict[str, FactoryCallback | None]

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        self.fields: dict[str, FactoryField] = {}
        self.mappings: dict[str, FactoryCallback | None] = {}
        self.callcounts: dict[int, int] = {}
        for slot in self.__slots__:
            value = getattr(meta, slot, None)
            if value is not None:
                setattr(self, slot, value)
        for name, value in kwargs.items():
            setattr(self, name, value)


class ModelFactoryMeta(type):
    def __new__(
        cls,
        factory_name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        meta_info_class: type[MetaInfo] = MetaInfo,
        model_validation: Literal["none", "warn", "error", "pedantic"] = "warn",
        **kwargs: Any,
    ) -> type[ModelFactory]:
        if not any(True for parent in bases if isinstance(parent, ModelFactoryMeta)):
            return super().__new__(cls, factory_name, bases, attrs, **kwargs)  # type: ignore

        faker = make_faker()
        meta_class: Any = attrs.pop("Meta", None)
        fields: dict[str, FactoryField] = {}
        mappings: dict[str, FactoryCallback | None] = {}

        current_mapping: dict[str, FactoryCallback | None] = (
            getattr(meta_class, "mappings", None) or {}
        )
        for name, mapping in current_mapping.items():
            mappings.setdefault(name, mapping)

        for base in bases:
            for sub in getmro(base):
                meta: Any = getattr(sub, "meta", None)
                if isinstance(meta, MetaInfo):
                    for name, mapping in meta.mappings.items():
                        mappings.setdefault(name, mapping)
                    for name, field in meta.fields.items():
                        if field.no_copy:
                            continue
                        if not field.callback and field.get_field_type() not in mappings:
                            terminal.write_warning(
                                f'Mapping for field type "{field.get_field_type()}" not found.'
                            )
                        else:
                            fields.setdefault(name, field.__copy__())

        for name, mapping in DEFAULT_MAPPING.items():
            mappings.setdefault(name, mapping)

        db_model: type[Model] | str | None = getattr(meta_class, "model", None)
        if db_model is None:
            raise InvalidModelError("Model is required for a factory.") from None
        if isinstance(db_model, str):
            module_path, class_name = db_model.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            db_model = cast(type[Model], getattr(module, class_name))
        if not is_class_and_subclass(db_model, Model):
            db_model_name = db_model.__name__ if isclass(db_model) else type(db_model).__name__
            raise InvalidModelError(f"Class {db_model_name} is not a Saffier model.") from None

        meta_info = meta_info_class(model=db_model, faker=faker, mappings=mappings)
        defaults: dict[str, Any] = {}

        for key in list(attrs.keys()):
            if key in ("meta", "exclude_autoincrement"):
                continue
            value: Any = attrs.get(key)
            if isinstance(value, FactoryField):
                value.original_name = key
                del attrs[key]
                value.name = field_name = value.name or key
                if (
                    not value.callback
                    and value.get_field_type(db_model_meta=db_model.meta) not in mappings
                ):
                    terminal.write_warning(
                        f'Mapping for field type "{value.get_field_type(db_model_meta=db_model.meta)}" not found.'
                    )
                else:
                    fields[field_name] = value
            elif key in db_model.meta.fields:
                defaults[key] = value

        for db_field_name in db_model.meta.fields:
            if db_field_name in fields:
                continue
            field = FactoryField(name=db_field_name, no_copy=True)
            field.original_name = db_field_name
            field_type = field.get_field_type(db_model_meta=db_model.meta)
            if field_type not in meta_info.mappings:
                terminal.write_warning(f'Mapping for field type "{field_type}" not found.')
                continue
            mapping_result = meta_info.mappings.get(field_type)
            if mapping_result:
                fields[field.name] = field

        meta_info.fields = fields
        attrs["meta"] = meta_info

        new_class = cast(
            type["ModelFactory"], super().__new__(cls, factory_name, bases, attrs, **kwargs)
        )
        new_class.__defaults__ = defaults

        for field in fields.values():
            field.owner = new_class

        if model_validation != "none":
            try:
                new_class().build(callcounts={})
            except ValidationError:
                if model_validation == "pedantic":
                    raise
            except Exception as exc:
                if model_validation in {"error", "pedantic"}:
                    raise
                terminal.write_warning(
                    f'"{factory_name}" failed producing a valid sample model: "{exc!r}".'
                )

        return new_class
