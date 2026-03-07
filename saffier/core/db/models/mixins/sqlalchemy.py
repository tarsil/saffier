from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import sqlalchemy

from saffier.core.db.fields import ForeignKey, ManyToManyField, OneToOneField, RefForeignKey
from saffier.core.db.relationships.related import RelatedField
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


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
        if column_key is None:
            raise AttributeError(name)
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
            aliases_str = ", ".join(f'"{alias}"' for alias in aliases)
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" is a relationship. '
                    f"Use foreign key column alias(es): {aliases_str}."
                )
            )
        if not field.has_column():
            raise ImproperlyConfigured(
                detail=(
                    f'Field "{name}" on "{cls.__name__}" does not define SQLAlchemy columns and '
                    "cannot be used in SQLAlchemy Core expressions."
                )
            )
        return cls._get_sqlalchemy_column_by_key(name=name, column_key=name)

    @classmethod
    def _lookup_sqlalchemy_foreign_key_alias(cls: type[Model], name: str) -> str | None:
        for field_name in cls.meta.foreign_key_fields:
            for alias, column_key in cls._iter_foreign_key_aliases(field_name):
                if alias == name and alias not in cls.meta.fields:
                    return column_key
        return None

    @classmethod
    def _foreign_key_aliases_for_field(cls: type[Model], field_name: str) -> tuple[str, ...]:
        return tuple(alias for alias, _ in cls._iter_foreign_key_aliases(field_name))

    @classmethod
    def _iter_foreign_key_aliases(
        cls: type[Model], field_name: str
    ) -> tuple[tuple[str, str], ...]:
        field = cls.meta.fields[field_name]
        suffix = getattr(field.target, "pkname", "id")
        return ((f"{field_name}_{suffix}", field_name),)

    @classmethod
    def _get_sqlalchemy_column_by_key(
        cls: type[Model], *, name: str, column_key: str
    ) -> sqlalchemy.Column[Any]:
        try:
            return cast(sqlalchemy.Column[Any], cls.table.columns[column_key])
        except AttributeError as exc:
            raise AttributeError(name) from exc
        except KeyError as exc:
            raise ImproperlyConfigured(
                detail=(
                    f'Column key "{column_key}" for compatibility attribute "{name}" is not '
                    f'available on model "{cls.__name__}".'
                )
            ) from exc
