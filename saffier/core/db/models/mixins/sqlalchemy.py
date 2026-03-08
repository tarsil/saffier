from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import sqlalchemy

from saffier.core.db.fields import ForeignKey, ManyToManyField, OneToOneField, RefForeignKey
from saffier.core.db.relationships.related import RelatedField
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model

_missing = object()


class SQLAlchemyModelMixin:
    """
    Opt-in compatibility mixin exposing scalar SQLAlchemy columns as class attributes.
    """

    __saffier_sqlalchemy_compatibility__: ClassVar[bool] = True

    @classmethod
    def _resolve_sqlalchemy_compatible_attribute(cls: type[Model], name: str) -> Any:
        field = cls.meta.fields.get(name)
        if field is not None:
            return cls._resolve_sqlalchemy_field_column(name=name, field=field)

        column_key = cls._lookup_sqlalchemy_foreign_key_alias(name)
        if column_key is _missing:
            raise AttributeError(name)
        if column_key is None:
            raise ImproperlyConfigured(
                detail=(
                    f'Foreign key alias "{name}" is ambiguous on model "{cls.__name__}". '
                    "Use explicit SQLAlchemy columns via Model.columns."
                )
            )
        return cls._get_sqlalchemy_column_by_key(name=name, column_key=column_key)

    @classmethod
    def _resolve_sqlalchemy_field_column(cls: type[Model], *, name: str, field: Any) -> Any:
        if isinstance(field, ManyToManyField):
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" is a many-to-many relation and does not '
                    "map to a scalar SQLAlchemy column."
                )
            )
        if isinstance(field, RelatedField):
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" is a reverse relation and cannot be used '
                    "as a SQLAlchemy column expression."
                )
            )
        if isinstance(field, RefForeignKey) and getattr(field, "is_model_reference", False):
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" is a RefForeignKey helper and does not '
                    "map to a SQLAlchemy table column."
                )
            )
        if isinstance(field, (ForeignKey, OneToOneField)):
            aliases = cls._foreign_key_aliases_for_field(name)
            if aliases:
                aliases_str = ", ".join(f'"{alias}"' for alias in aliases)
                raise ImproperlyConfigured(
                    detail=(
                        f'Field "{name}" on "{cls.__name__}" is a relationship. '
                        f"Use foreign key column alias(es): {aliases_str}."
                    )
                )
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" is a relationship and cannot be used as '
                    "a SQLAlchemy scalar column."
                )
            )

        columns = tuple(cls.meta.get_columns_for_name(name))
        if not columns:
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" does not define SQLAlchemy columns and '
                    "cannot be used in SQLAlchemy Core expressions."
                )
            )
        if len(columns) != 1:
            columns_str = ", ".join(f'"{column.key}"' for column in columns)
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" maps to multiple SQLAlchemy columns '
                    f"({columns_str}). Use a concrete column name."
                )
            )
        return cls._get_sqlalchemy_column_by_key(name=name, column_key=columns[0].key)

    @classmethod
    def _lookup_sqlalchemy_foreign_key_alias(cls: type[Model], name: str) -> str | None | object:
        alias_map: dict[str, str | None] = {}
        for field_name in cls.meta.foreign_key_fields:
            field = cls.meta.fields[field_name]
            if not isinstance(field, (ForeignKey, OneToOneField)):
                continue
            for alias, column_key in cls._iter_foreign_key_aliases(field_name, field):
                if alias in cls.meta.fields:
                    continue
                existing = alias_map.get(alias, _missing)
                if existing is _missing:
                    alias_map[alias] = column_key
                elif existing != column_key:
                    alias_map[alias] = None
        return alias_map.get(name, _missing)

    @classmethod
    def _foreign_key_aliases_for_field(cls: type[Model], field_name: str) -> tuple[str, ...]:
        field = cls.meta.fields[field_name]
        if not isinstance(field, (ForeignKey, OneToOneField)):
            return ()
        aliases: list[str] = []
        for alias, _ in cls._iter_foreign_key_aliases(field_name, field):
            if alias not in aliases:
                aliases.append(alias)
        return tuple(aliases)

    @classmethod
    def _iter_foreign_key_aliases(
        cls: type[Model], field_name: str, field: ForeignKey | OneToOneField
    ) -> tuple[tuple[str, str], ...]:
        aliases: list[tuple[str, str]] = []
        for column in cls.meta.get_columns_for_name(field_name):
            translated = field.from_fk_field_name(field_name, column.key)
            aliases.append((f"{field_name}_{translated}", column.key))
        return tuple(aliases)

    @classmethod
    def _get_sqlalchemy_column_by_key(
        cls: type[Model], *, name: str, column_key: str
    ) -> sqlalchemy.Column[Any]:
        try:
            table = cls.table
        except AttributeError as exc:
            raise ImproperlyConfigured(
                detail=(
                    f'Cannot resolve "{name}" on model "{cls.__name__}" because no table is '
                    "available. Ensure the model is bound to a registry."
                )
            ) from exc
        except KeyError as exc:
            raise ImproperlyConfigured(
                detail=(
                    f'Column key "{column_key}" for compatibility attribute "{name}" is not '
                    f'available on model "{cls.__name__}".'
                )
            ) from exc
        try:
            return cast(sqlalchemy.Column[Any], table.columns[column_key])
        except KeyError as exc:
            raise ImproperlyConfigured(
                detail=(
                    f'Column key "{column_key}" for compatibility attribute "{name}" is not '
                    f'available on model "{cls.__name__}".'
                )
            ) from exc
