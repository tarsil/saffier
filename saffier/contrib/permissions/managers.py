from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy

from saffier.core.db.models.managers import Manager
from saffier.core.db.querysets.clauses import and_


def _apply_or_clauses(base_queryset: Any, clauses: list[dict[str, Any]]) -> Any:
    if not clauses:
        return base_queryset.filter(and_())
    queryset = base_queryset.filter(**clauses[0])
    for clause in clauses[1:]:
        queryset = queryset.or_(**clause)
    return queryset


def _normalize_model_values(values: Sequence[Any | None] | Any | None) -> list[Any | None] | None:
    if values is None:
        return None
    if isinstance(values, (list, tuple)):
        return list(values)
    return [values]


def _in_or_null(column: Any, values: list[Any | None]) -> Any:
    has_null = any(value is None for value in values)
    non_null_values = [value for value in values if value is not None]
    if has_null and non_null_values:
        return sqlalchemy.or_(column.in_(non_null_values), column.is_(None))
    if has_null:
        return column.is_(None)
    return column.in_(non_null_values)


class PermissionManager(Manager):
    def _permission_pk_subquery(
        self,
        permissions: Sequence[str],
        model_names: Sequence[str | None] | None = None,
        objects: Sequence[Any | None] | None = None,
    ) -> Any:
        permission_table = self.owner.table
        permission_pk = self.owner.pkname
        expression = sqlalchemy.select(permission_table.c[permission_pk]).where(
            permission_table.c.name.in_(permissions)
        )

        if model_names is not None and "name_model" in permission_table.c:
            expression = expression.where(
                _in_or_null(permission_table.c.name_model, list(model_names))
            )
        elif model_names is not None and "obj" in permission_table.c:
            expression = expression.where(_in_or_null(permission_table.c.obj, list(model_names)))

        if objects is not None and "obj" in permission_table.c:
            object_values = [obj.pk if hasattr(obj, "pk") else obj for obj in objects]
            expression = expression.where(_in_or_null(permission_table.c.obj, object_values))

        return expression

    def permissions_of(self, sources: Sequence[Any] | Any) -> Any:
        if not isinstance(sources, (list, tuple)):
            sources = [sources]
        if len(sources) == 0:
            return self.filter(and_())

        user_field = self.owner.meta.fields["users"]
        group_field = self.owner.meta.fields.get("groups")
        permission_column_name = self.owner.__name__.lower()
        user_column_name = user_field.target.__name__.lower()
        clauses: list[dict[str, Any]] = []

        for source in sources:
            if isinstance(source, user_field.target):
                user_direct_subquery = sqlalchemy.select(
                    user_field.through.table.c[permission_column_name]
                ).where(user_field.through.table.c[user_column_name] == source.pk)
                clauses.append({"pk__in": user_direct_subquery})

                if group_field is not None:
                    group_column_name = group_field.target.__name__.lower()
                    group_user_field = group_field.target.meta.fields[self.owner.users_field_group]
                    group_user_column_name = group_user_field.target.__name__.lower()
                    group_ids_subquery = sqlalchemy.select(
                        group_user_field.through.table.c[group_column_name]
                    ).where(group_user_field.through.table.c[group_user_column_name] == source.pk)
                    permission_from_group_subquery = sqlalchemy.select(
                        group_field.through.table.c[permission_column_name]
                    ).where(group_field.through.table.c[group_column_name].in_(group_ids_subquery))
                    clauses.append({"pk__in": permission_from_group_subquery})
            elif group_field is not None and isinstance(source, group_field.target):
                group_column_name = group_field.target.__name__.lower()
                permission_from_group_subquery = sqlalchemy.select(
                    group_field.through.table.c[permission_column_name]
                ).where(group_field.through.table.c[group_column_name] == source.pk)
                clauses.append({"pk__in": permission_from_group_subquery})
            else:
                raise ValueError(f"Invalid source: {source}.")

        return _apply_or_clauses(self, clauses)

    def users(
        self,
        permissions: Sequence[str] | str,
        model_names: Sequence[str | None] | str | None = None,
        objects: Sequence[Any | None] | Any | None = None,
        include_null_model_name: bool = True,
        include_null_object: bool = True,
    ) -> Any:
        if isinstance(permissions, str):
            permissions = [permissions]

        normalized_model_names = _normalize_model_values(model_names)
        if normalized_model_names is not None and include_null_model_name:
            normalized_model_names = [*normalized_model_names, None]

        normalized_objects = _normalize_model_values(objects)
        if normalized_objects is not None and include_null_object:
            normalized_objects = [*normalized_objects, None]
        if normalized_objects is not None and len(normalized_objects) == 0:
            user_field = self.owner.meta.fields["users"]
            return user_field.target.query.filter(and_())

        permission_subquery = self._permission_pk_subquery(
            permissions,
            normalized_model_names,
            normalized_objects,
        )

        user_field = self.owner.meta.fields["users"]
        group_field = self.owner.meta.fields.get("groups")

        permission_column_name = self.owner.__name__.lower()
        user_column_name = user_field.target.__name__.lower()

        direct_user_ids = sqlalchemy.select(user_field.through.table.c[user_column_name]).where(
            user_field.through.table.c[permission_column_name].in_(permission_subquery)
        )

        clauses: list[dict[str, Any]] = [{"pk__in": direct_user_ids}]

        if group_field is not None:
            group_column_name = group_field.target.__name__.lower()
            group_user_field = group_field.target.meta.fields[self.owner.users_field_group]
            group_user_column_name = group_user_field.target.__name__.lower()
            permission_group_ids = sqlalchemy.select(
                group_field.through.table.c[group_column_name]
            ).where(group_field.through.table.c[permission_column_name].in_(permission_subquery))
            grouped_user_ids = sqlalchemy.select(
                group_user_field.through.table.c[group_user_column_name]
            ).where(group_user_field.through.table.c[group_column_name].in_(permission_group_ids))
            clauses.append({"pk__in": grouped_user_ids})

        return _apply_or_clauses(user_field.target.query, clauses)

    def groups(
        self,
        permissions: Sequence[str] | str,
        model_names: Sequence[str | None] | str | None = None,
        objects: Sequence[Any | None] | Any | None = None,
        include_null_model_name: bool = True,
        include_null_object: bool = True,
    ) -> Any:
        if isinstance(permissions, str):
            permissions = [permissions]

        normalized_model_names = _normalize_model_values(model_names)
        if normalized_model_names is not None and include_null_model_name:
            normalized_model_names = [*normalized_model_names, None]

        normalized_objects = _normalize_model_values(objects)
        if normalized_objects is not None and include_null_object:
            normalized_objects = [*normalized_objects, None]
        if normalized_objects is not None and len(normalized_objects) == 0:
            group_field = self.owner.meta.fields["groups"]
            return group_field.target.query.filter(and_())

        permission_subquery = self._permission_pk_subquery(
            permissions,
            normalized_model_names,
            normalized_objects,
        )

        group_field = self.owner.meta.fields["groups"]
        permission_column_name = self.owner.__name__.lower()
        group_column_name = group_field.target.__name__.lower()
        group_ids = sqlalchemy.select(group_field.through.table.c[group_column_name]).where(
            group_field.through.table.c[permission_column_name].in_(permission_subquery)
        )
        return group_field.target.query.filter(pk__in=group_ids)
