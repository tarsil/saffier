import copy
from typing import Any

import sqlalchemy

from saffier.fields import Field
from saffier.types import DictAny


class BaseMeta:
    ...


class BaseModelMeta(type):
    """
    Metaclass for the Saffier models and managing the Meta class.
    """

    def __new__(cls, name: str, bases: Any, attrs: Any, **kwargs: DictAny):
        model_class = super().__new__

        # Ensure the initialization is only performed for subclasses of Model
        parents = [parent for parent in bases if isinstance(parent, BaseModelMeta)]
        if not parents:
            return model_class(cls, name, bases, attrs, **kwargs)

        new_class = model_class(cls, name, bases, attrs, **kwargs)

        # Set the metaclass
        attr_meta = attrs.pop("Meta", None)
        if not attr_meta:
            return new_class

        # Abstract field from meta
        abstract = getattr(attr_meta, "abstract", False)
        meta = attr_meta or getattr(new_class, "Meta", BaseMeta)

        if getattr(meta, "registry", None) is None:
            raise RuntimeError("registry is missing from the Meta class.")

        registry = meta.registry
        new_class.database = registry.database
        registry.models[name] = new_class

        # Making sure the tablename is always set if the value is not provided
        if getattr(meta, "tablename", None) is None:
            tablename = f"{name.lower()}s"
            setattr(new_class.Meta, "tablename", tablename)

        # Set the parents of the new_class
        setattr(meta, "parents", parents)

        inherited_attributes = set()
        for base in new_class.mro():
            # Models without the Meta are not considered models anyway
            if base not in parents or not hasattr(base, "Meta"):
                for k, v in base.__dict__.items():
                    if v is not None:
                        inherited_attributes.add(v)
                continue

            parent_fields = base.fields
            base_parents = base.Meta.parents.copy()
            for name, field in parent_fields.items():
                if name not in new_class.__dict__ and name not in inherited_attributes:
                    breakpoint()
                    new_field = copy.deepcopy(field)
                    setattr(new_class, name, new_field)
                    attrs[k] = new_field

        fields = {}
        for name, field in attrs.items():
            if (not name.startswith("__") and not name.endswith("__")) and isinstance(
                field, Field
            ):
                fields[name] = field
                setattr(field, "registry", registry)
                if field.primary_key:
                    new_class.pkname = name

        setattr(new_class, "fields", fields)
        return new_class

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
