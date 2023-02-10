from typing import Any

import sqlalchemy
from pydantic import Field

from saffier.core.schemas import Schema
from saffier.core.utils import ModelUtil
from saffier.fields import Field
from saffier.managers import ModelManager
from saffier.types import DictAny


class BaseModelMeta(type):
    """
    Metaclass for the Saffier models
    """

    def __new__(cls, name: str, bases: Any, attrs: Any):
        model_class = super().__new__(cls, name, bases, attrs)

        # Set the metaclass
        attr_meta = attrs.pop("Meta", None)
        if not attr_meta:
            return model_class

        if getattr(attr_meta, "registry", None) is None:
            raise RuntimeError("registry is missing from the Meta class.")

        registry = attr_meta.registry
        model_class.database = registry.database
        registry.models[name] = model_class

        # Making sure the tablename is always set if the value is not provided
        if getattr(attr_meta, "tablename", None) is None:
            tablename = f"{name.lower()}s"
            setattr(model_class.Meta, "tablename", tablename)

        fields = {}
        for name, field in attrs.items():
            if (not name.startswith("_") and not name.endswith("_")) and isinstance(field, Field):
                fields[name] = field
                setattr(field, "registry", registry)
                if field.primary_key:
                    model_class.pkname = name

        setattr(model_class, "fields", fields)
        return model_class

    @property
    def table(cls):
        if not hasattr(cls, "_table"):
            cls._table = cls.build_table()
        return cls._table

    @property
    def columns(cls) -> sqlalchemy.sql.ColumnCollection:
        return cls._table.columns


class ModelMeta(metaclass=BaseModelMeta):
    ...
