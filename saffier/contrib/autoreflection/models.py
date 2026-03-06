from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, ClassVar

import sqlalchemy

import saffier

from .metaclasses import AutoReflectionMeta, AutoReflectionMetaInfo

if TYPE_CHECKING:
    from saffier.core.connection.registry import Registry


class AutoReflectModel(saffier.ReflectModel, metaclass=AutoReflectionMeta):
    meta: ClassVar[AutoReflectionMetaInfo]

    class Meta:
        abstract = True
        is_pattern_model = True

    @classmethod
    def _pattern_fields(cls) -> dict[str, Any]:
        fields = dict(cls.meta.fields_mapping)
        if set(fields.keys()) == {"id"}:
            field = fields["id"]
            if (
                isinstance(field, saffier.BigIntegerField)
                and field.primary_key
                and field.autoincrement
            ):
                return {}
        return fields

    @classmethod
    def fields_not_supported_by_table(cls, table: sqlalchemy.Table) -> bool:
        table_columns = {column.name for column in table.columns}
        pattern_fields = cls._pattern_fields()
        return any(field_name not in table_columns for field_name in pattern_fields)

    @classmethod
    def create_reflected_model(
        cls,
        *,
        table: sqlalchemy.Table,
        registry: Registry,
        database: Any,
        name: str | None = None,
    ) -> type[saffier.ReflectModel]:
        model_name = name or cls.meta.template(table)
        attributes: dict[str, Any] = {"__module__": cls.__module__}
        pattern_fields = cls._pattern_fields()
        if pattern_fields:
            for key, field in pattern_fields.items():
                attributes[key] = copy.copy(field)
        else:
            for column in table.columns:
                attributes[column.name] = cls._column_to_field(column)

        meta_attrs = {
            "registry": registry,
            "tablename": table.name,
            "abstract": False,
            "reflect": True,
            "is_pattern_model": False,
        }
        attributes["Meta"] = type("Meta", (), meta_attrs)

        model = type(model_name, (saffier.ReflectModel,), attributes)
        model.database = database
        model._table = table
        if table.schema is not None:
            model.__using_schema__ = table.schema
        return model

    @classmethod
    def _column_to_field(cls, column: sqlalchemy.Column[Any]) -> Any:
        kwargs = {
            "null": bool(column.nullable),
            "primary_key": bool(column.primary_key),
            "unique": bool(column.unique),
            "index": bool(column.index),
        }
        if column.primary_key and column.autoincrement is True:
            kwargs["autoincrement"] = True

        ctype = column.type

        if isinstance(ctype, sqlalchemy.BigInteger):
            return saffier.BigIntegerField(**kwargs)
        if isinstance(ctype, sqlalchemy.SmallInteger):
            return saffier.SmallIntegerField(**kwargs)
        if isinstance(ctype, sqlalchemy.Integer):
            return saffier.IntegerField(**kwargs)
        if isinstance(ctype, sqlalchemy.Boolean):
            return saffier.BooleanField(**kwargs)
        if isinstance(ctype, sqlalchemy.Float):
            return saffier.FloatField(**kwargs)
        if isinstance(ctype, sqlalchemy.Numeric):
            return saffier.DecimalField(
                max_digits=ctype.precision or 20,
                decimal_places=ctype.scale or 6,
                **kwargs,
            )
        if isinstance(ctype, sqlalchemy.DateTime):
            return saffier.DateTimeField(**kwargs)
        if isinstance(ctype, sqlalchemy.Date):
            return saffier.DateField(**kwargs)
        if isinstance(ctype, sqlalchemy.Time):
            return saffier.TimeField(**kwargs)
        if isinstance(ctype, sqlalchemy.Interval):
            return saffier.DurationField(**kwargs)
        if isinstance(ctype, sqlalchemy.LargeBinary):
            return saffier.BinaryField(max_length=ctype.length, **kwargs)
        if isinstance(ctype, sqlalchemy.UUID):
            return saffier.UUIDField(**kwargs)
        if isinstance(ctype, sqlalchemy.JSON):
            return saffier.JSONField(**kwargs)
        if isinstance(ctype, sqlalchemy.Text):
            return saffier.TextField(**kwargs)
        if isinstance(ctype, sqlalchemy.String):
            return saffier.CharField(max_length=ctype.length or 255, **kwargs)

        return saffier.TextField(**kwargs)
