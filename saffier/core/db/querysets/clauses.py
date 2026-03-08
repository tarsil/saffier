from __future__ import annotations

from typing import Any

import sqlalchemy

from saffier.conf import settings
from saffier.core.db import fields as saffier_fields
from saffier.core.db.relationships.related import RelatedField
from saffier.core.db.relationships.utils import crawl_relationship
from saffier.core.utils.db import hash_tablekey
from saffier.core.utils.sync import run_sync

DEFAULT_ESCAPE_CHARACTERS = ("%", "_")


def _normalize_lookup_path(key: str, embed_parent: tuple[str, str] | None) -> str:
    if not embed_parent:
        return key
    if embed_parent[1] and key.startswith(embed_parent[1]):
        return key.removeprefix(embed_parent[1]).removeprefix("__")
    return f"{embed_parent[0]}__{key}"


def _normalize_lookup_value(value: Any) -> Any:
    if hasattr(value, "pk"):
        return value.pk
    return value


def _build_composite_exact_clause(
    column_values: dict[sqlalchemy.Column[Any], Any],
) -> Any:
    clauses = [column == value for column, value in column_values.items()]
    if not clauses:
        return sqlalchemy.true()
    if len(clauses) == 1:
        return clauses[0]
    return sqlalchemy.and_(*clauses)


def _build_composite_in_clause(
    rows: list[dict[sqlalchemy.Column[Any], Any]],
) -> Any:
    clauses = [_build_composite_exact_clause(row) for row in rows]
    if not clauses:
        return sqlalchemy.false()
    if len(clauses) == 1:
        return clauses[0]
    return sqlalchemy.or_(*clauses)


def build_lookup_clauses(
    model_class: Any,
    table: sqlalchemy.Table,
    kwargs: dict[str, Any],
    *,
    escape_characters: tuple[str, ...] = DEFAULT_ESCAPE_CHARACTERS,
    using_schema: str | None = None,
    embed_parent: tuple[str, str] | None = None,
    model_database: Any | None = None,
) -> tuple[list[Any], list[str]]:
    """
    Build SQLAlchemy filter clauses from Saffier lookup kwargs.

    Returns:
        A tuple containing:
        - list of generated SQLAlchemy clauses
        - list of inferred ``select_related`` paths
    """
    clauses: list[Any] = []
    select_related: list[str] = []
    clean_kwargs = dict(kwargs)

    if "pk" in clean_kwargs:
        pk_value = clean_kwargs.pop("pk")
        if len(tuple(getattr(model_class, "pknames", ()))) > 1:
            clean_kwargs["pk__exact"] = pk_value
        else:
            clean_kwargs[model_class.pkname] = pk_value

    for raw_key, value in clean_kwargs.items():
        key = _normalize_lookup_path(raw_key, embed_parent)
        field_obj = None
        composite_fk = None
        related_model = model_class
        root_model_class = model_class
        composite_pk_columns: dict[str, sqlalchemy.Column[Any]] | None = None
        if "__" in key:
            crawl_result = crawl_relationship(model_class, key, model_database=model_database)
            op = crawl_result.operator or "exact"
            related_model = crawl_result.model_class
            if crawl_result.cross_db_remainder:
                relation_field = model_class.fields.get(crawl_result.field_name)
                if not isinstance(
                    relation_field,
                    (saffier_fields.ForeignKey, saffier_fields.OneToOneField),
                ):
                    raise ValueError(
                        f"Cross-database lookup requires a foreign key field, got {crawl_result.field_name!r}."
                    )
                remote_fields = tuple(relation_field.related_columns.keys())
                sub_queryset = relation_field.target.query.filter(
                    **{crawl_result.cross_db_remainder: value}
                )
                if len(remote_fields) == 1:
                    sub_results = run_sync(
                        sub_queryset.values_list(fields=[remote_fields[0]], flat=True)
                    )
                    clauses.append(
                        table.columns[
                            relation_field.get_column_names(crawl_result.field_name)[0]
                        ].in_(sub_results)
                    )
                else:
                    sub_results = run_sync(sub_queryset.values_list(fields=list(remote_fields)))
                    clauses.append(
                        _build_composite_in_clause(
                            [
                                {
                                    table.columns[column_name]: row[idx]
                                    for idx, column_name in enumerate(
                                        relation_field.get_column_names(crawl_result.field_name)
                                    )
                                }
                                for row in sub_results
                            ]
                        )
                    )
                continue
            direct_relation_field = None
            if crawl_result.forward_path and "__" not in crawl_result.forward_path:
                candidate = model_class.fields.get(crawl_result.forward_path)
                if isinstance(
                    candidate, (saffier_fields.ForeignKey, saffier_fields.OneToOneField)
                ):
                    direct_relation_field = candidate
            if (
                direct_relation_field is not None
                and (
                    crawl_result.field_name == "pk"
                    or crawl_result.field_name in getattr(related_model, "pknames", ())
                )
                and op in {"exact", "in"}
            ):
                value = _normalize_lookup_value(value)
                column_names = direct_relation_field.get_column_names(crawl_result.forward_path)
                if op == "exact":
                    if crawl_result.field_name == "pk" or len(column_names) > 1:
                        payload = direct_relation_field.clean(
                            crawl_result.forward_path,
                            value,
                            for_query=True,
                        )
                    else:
                        payload = {column_names[0]: value}
                    clauses.append(
                        _build_composite_exact_clause(
                            {
                                table.columns[column_name]: payload.get(column_name)
                                for column_name in column_names
                            }
                        )
                    )
                else:
                    values = value if isinstance(value, (list, tuple, set)) else [value]
                    rows = []
                    for item in values:
                        if crawl_result.field_name == "pk" or len(column_names) > 1:
                            payload = direct_relation_field.clean(
                                crawl_result.forward_path,
                                item,
                                for_query=True,
                            )
                        else:
                            payload = {column_names[0]: _normalize_lookup_value(item)}
                        rows.append(
                            {
                                table.columns[column_name]: payload.get(column_name)
                                for column_name in column_names
                            }
                        )
                    clauses.append(_build_composite_in_clause(rows))
                continue
            related_table = (
                related_model.table_schema(using_schema)
                if using_schema is not None
                else related_model.table
            )
            if crawl_result.forward_path and related_model is root_model_class:
                related_table = related_table.alias(
                    hash_tablekey(
                        tablekey=related_model.meta.tablename,
                        prefix=crawl_result.forward_path,
                    )
                )
            if crawl_result.field_name == "pk":
                field_name = "pk"
                if len(tuple(getattr(related_model, "pknames", ()))) > 1:
                    composite_pk_columns = {
                        pk_name: related_table_column
                        for pk_name in related_model.pknames
                        if (related_table_column := getattr(related_table.c, pk_name, None))
                        is not None
                    }
                else:
                    field_name = related_model.pkname
                    field_obj = related_model.fields.get(field_name)
            else:
                field_name = crawl_result.field_name
                field_obj = related_model.fields.get(field_name)
            if crawl_result.forward_path and crawl_result.forward_path not in select_related:
                select_related.append(crawl_result.forward_path)
            if composite_pk_columns is None:
                try:
                    column = related_table.columns[field_name]
                except KeyError as error:
                    attr = getattr(related_model, field_name, None)
                    if isinstance(attr, RelatedField):
                        column = related_table.columns[settings.default_related_lookup_field]
                        field_obj = related_model.fields.get(settings.default_related_lookup_field)
                    else:
                        raise KeyError(str(error)) from error
        else:
            op = "exact"
            field_name = key
            field_obj = model_class.fields.get(field_name)
            if isinstance(field_obj, (saffier_fields.ForeignKey, saffier_fields.OneToOneField)):
                composite_fk = field_obj if len(field_obj.related_columns) > 1 else None
            if composite_fk is None:
                try:
                    column = table.columns[field_name]
                except KeyError as error:
                    try:
                        related_model = getattr(model_class, field_name).related_to
                        related_table = (
                            related_model.table_schema(using_schema)
                            if using_schema is not None
                            else related_model.table
                        )
                        column = related_table.columns[settings.default_related_lookup_field]
                        field_obj = related_model.fields.get(settings.default_related_lookup_field)
                    except AttributeError:
                        raise KeyError(str(error)) from error

        value = _normalize_lookup_value(value)

        if composite_pk_columns is not None and op in {"exact", "in"}:
            if op == "exact":
                payload = _normalize_lookup_value(value)
                if not isinstance(payload, dict):
                    raise ValueError("Composite primary key lookups require mapping values.")
                clauses.append(
                    _build_composite_exact_clause(
                        {
                            column: payload.get(pk_name)
                            for pk_name, column in composite_pk_columns.items()
                        }
                    )
                )
            else:
                values = value if isinstance(value, (list, tuple, set)) else [value]
                rows = []
                for item in values:
                    payload = _normalize_lookup_value(item)
                    if not isinstance(payload, dict):
                        raise ValueError(
                            "Composite primary key __in lookups require mapping values."
                        )
                    rows.append(
                        {
                            column: payload.get(pk_name)
                            for pk_name, column in composite_pk_columns.items()
                        }
                    )
                clauses.append(_build_composite_in_clause(rows))
            continue

        if composite_fk is not None and op in {"exact", "in"}:
            column_names = composite_fk.get_column_names(field_name)
            if op == "exact":
                payload = composite_fk.clean(field_name, value, for_query=True)
                clauses.append(
                    _build_composite_exact_clause(
                        {
                            table.columns[column_name]: payload.get(column_name)
                            for column_name in column_names
                        }
                    )
                )
            else:
                values = value if isinstance(value, (list, tuple, set)) else [value]
                rows = []
                for item in values:
                    payload = composite_fk.clean(field_name, item, for_query=True)
                    rows.append(
                        {
                            table.columns[column_name]: payload.get(column_name)
                            for column_name in column_names
                        }
                    )
                clauses.append(_build_composite_in_clause(rows))
            continue

        op_attr = settings.filter_operators.get(op, op)
        has_escaped_character = False

        if op in {"contains", "icontains"} and isinstance(value, str):
            has_escaped_character = any(char in value for char in escape_characters)
            if has_escaped_character:
                for char in escape_characters:
                    value = value.replace(char, f"\\{char}")
            value = f"%{value}%"

        if field_obj is not None:
            cleaned_value = field_obj.clean(field_name, value, for_query=True)
            if field_name in cleaned_value:
                value = cleaned_value[field_name]
            elif column.key in cleaned_value:
                value = cleaned_value[column.key]
            clause = field_obj.operator_to_clause(
                field_name=column.key,
                operator=op,
                table=column.table,
                value=value,
            )
        else:
            clause = getattr(column, op_attr)(value)
        if hasattr(clause, "modifiers"):
            clause.modifiers["escape"] = "\\" if has_escaped_character else None
        clauses.append(clause)

    return clauses, select_related


class Q:
    """
    Composable query helper for Saffier lookups.

    Supports keyword lookups and SQLAlchemy expressions, and can be combined using:
    ``&`` (AND), ``|`` (OR), and ``~`` (NOT).
    """

    __slots__ = ("args", "kwargs", "connector", "negated")

    def __init__(
        self,
        *args: Any,
        _connector: str = "AND",
        _negated: bool = False,
        **kwargs: Any,
    ) -> None:
        self.args = list(args)
        self.kwargs = dict(kwargs)
        self.connector = _connector
        self.negated = _negated

    def _combine(self, other: Any, connector: str) -> Q:
        if not isinstance(other, Q):
            other = Q(other)
        return Q(self, other, _connector=connector)

    def __and__(self, other: Any) -> Q:
        return self._combine(other, "AND")

    def __rand__(self, other: Any) -> Q:
        return self._combine(other, "AND")

    def __or__(self, other: Any) -> Q:
        return self._combine(other, "OR")

    def __ror__(self, other: Any) -> Q:
        return self._combine(other, "OR")

    def __invert__(self) -> Q:
        return Q(*self.args, _connector=self.connector, _negated=not self.negated, **self.kwargs)

    def resolve(self, queryset: Any) -> tuple[Any, list[str]]:
        clauses: list[Any] = []
        select_related: list[str] = []
        escape_characters = tuple(
            getattr(queryset, "ESCAPE_CHARACTERS", DEFAULT_ESCAPE_CHARACTERS)
        )

        for arg in self.args:
            if isinstance(arg, Q):
                clause, related = arg.resolve(queryset)
                clauses.append(clause)
                for path in related:
                    if path not in select_related:
                        select_related.append(path)
            else:
                clauses.append(arg)

        if self.kwargs:
            kw_clauses, related = build_lookup_clauses(
                queryset.model_class,
                queryset.table,
                self.kwargs,
                escape_characters=escape_characters,
                using_schema=getattr(queryset, "using_schema", None),
                embed_parent=getattr(queryset, "embed_parent_filters", None),
                model_database=getattr(queryset, "database", None),
            )
            clauses.extend(kw_clauses)
            for path in related:
                if path not in select_related:
                    select_related.append(path)

        if not clauses:
            clause = sqlalchemy.true() if self.connector == "AND" else sqlalchemy.false()
        elif len(clauses) == 1:
            clause = clauses[0]
        elif self.connector == "AND":
            clause = sqlalchemy.and_(*clauses)
        else:
            clause = sqlalchemy.or_(*clauses)

        if self.negated:
            clause = sqlalchemy.not_(clause)

        return clause, select_related

    def __repr__(self) -> str:
        return (
            f"Q(connector={self.connector!r}, negated={self.negated!r}, "
            f"args={self.args!r}, kwargs={self.kwargs!r})"
        )


def or_(*args: Any, **kwargs: Any) -> Any:
    """Return a raw SQLAlchemy `OR` clause.

    This helper mirrors `sqlalchemy.or_` so callers can import the clause
    builder from Saffier's queryset namespace without reaching into SQLAlchemy
    directly.
    """
    return sqlalchemy.or_(*args, **kwargs)


def and_(*args: Any, **kwargs: Any) -> Any:
    """Return a raw SQLAlchemy `AND` clause.

    This helper mirrors `sqlalchemy.and_` so callers can compose manual clause
    trees alongside regular Saffier lookups.
    """
    return sqlalchemy.and_(*args, **kwargs)


def not_(*args: Any, **kwargs: Any) -> Any:
    """Return a raw SQLAlchemy `NOT` clause.

    This helper mirrors `sqlalchemy.not_` for manual clause composition inside
    queryset filters.
    """
    return sqlalchemy.not_(*args, **kwargs)
