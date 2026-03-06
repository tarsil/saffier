from __future__ import annotations

from inspect import getmro
from typing import Any, cast

from saffier.core.db.models import Model
from saffier.testing.exceptions import InvalidModelError

from .fields import FactoryField
from .mappings import DEFAULT_MAPPING


class MetaInfo:
    __slots__ = ("model", "fields", "faker", "mappings")

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        self.fields: dict[str, FactoryField] = {}
        self.mappings: dict[str, Any] = {}
        for slot in self.__slots__:
            value = getattr(meta, slot, None)
            if value is not None:
                setattr(self, slot, value)
        for key, value in kwargs.items():
            setattr(self, key, value)


class ModelFactoryMeta(type):
    def __new__(
        cls,
        factory_name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        meta_info_class: type[MetaInfo] = MetaInfo,
        **kwargs: Any,
    ) -> Any:
        if not any(True for parent in bases if isinstance(parent, ModelFactoryMeta)):
            return super().__new__(cls, factory_name, bases, attrs, **kwargs)

        try:
            from faker import Faker
        except ImportError:
            raise ImportError('"Faker" is required for ModelFactory.') from None

        faker = Faker()
        meta_class = attrs.pop("Meta", None)
        db_model = getattr(meta_class, "model", None)
        if db_model is None:
            raise InvalidModelError("Model is required for a factory.")
        if not isinstance(db_model, type) or not issubclass(db_model, Model):
            raise InvalidModelError(f"{db_model!r} is not a Saffier model.")

        inherited_fields: dict[str, FactoryField] = {}
        inherited_mappings: dict[str, Any] = {}
        for base in bases:
            for sub in getmro(base):
                meta = getattr(sub, "meta", None)
                if isinstance(meta, MetaInfo):
                    for name, field in meta.fields.items():
                        if field.no_copy:
                            continue
                        inherited_fields.setdefault(name, field.__copy__())
                    for key, value in meta.mappings.items():
                        inherited_mappings.setdefault(key, value)

        mappings = {
            **DEFAULT_MAPPING,
            **inherited_mappings,
            **(getattr(meta_class, "mappings", {}) or {}),
        }
        fields = dict(inherited_fields)
        defaults: dict[str, Any] = {}

        for key in list(attrs.keys()):
            value = attrs.get(key)
            if isinstance(value, FactoryField):
                field = value
                field.original_name = key
                del attrs[key]
                field.name = field.name or key
                fields[field.name] = field
            elif key in db_model.fields:
                defaults[key] = value

        for field_name, db_field in db_model.fields.items():
            if field_name in fields:
                continue
            field_type = type(db_field).__name__
            if field_type not in mappings:
                continue
            generated = FactoryField(name=field_name, no_copy=True, field_type=field_type)
            generated.original_name = field_name
            fields[field_name] = generated

        meta_info = meta_info_class(model=db_model, faker=faker, mappings=mappings)
        meta_info.fields = fields
        attrs["meta"] = meta_info
        new_class = cast(type[Any], super().__new__(cls, factory_name, bases, attrs, **kwargs))
        new_class.__defaults__ = defaults

        for field in fields.values():
            field.owner = new_class
        return new_class
