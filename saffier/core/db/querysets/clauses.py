from __future__ import annotations

from typing import Any

import sqlalchemy

from saffier.conf import settings
from saffier.core.db.relationships.related import RelatedField
from saffier.core.db.relationships.utils import crawl_relationship

DEFAULT_ESCAPE_CHARACTERS = ("%", "_")


def _normalize_lookup_path(key: str, embed_parent: tuple[str, str] | None) -> str:
    if not embed_parent:
        return key
    if embed_parent[1] and key.startswith(embed_parent[1]):
        return key.removeprefix(embed_parent[1]).removeprefix("__")
    return f"{embed_parent[0]}__{key}"


def build_lookup_clauses(
    model_class: Any,
    table: sqlalchemy.Table,
    kwargs: dict[str, Any],
    *,
    escape_characters: tuple[str, ...] = DEFAULT_ESCAPE_CHARACTERS,
    using_schema: str | None = None,
    embed_parent: tuple[str, str] | None = None,
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
        clean_kwargs[model_class.pkname] = clean_kwargs.pop("pk")

    for raw_key, value in clean_kwargs.items():
        key = _normalize_lookup_path(raw_key, embed_parent)
        field_obj = None
        if "__" in key:
            crawl_result = crawl_relationship(model_class, key)
            op = crawl_result.operator or "exact"
            related_model = crawl_result.model_class
            field_name = (
                related_model.pkname if crawl_result.field_name == "pk" else crawl_result.field_name
            )
            field_obj = related_model.fields.get(field_name)
            if crawl_result.forward_path and crawl_result.forward_path not in select_related:
                select_related.append(crawl_result.forward_path)
            related_table = (
                related_model.table_schema(using_schema)
                if using_schema is not None
                else related_model.table
            )
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

        op_attr = settings.filter_operators[op]
        has_escaped_character = False

        if op in {"contains", "icontains"} and isinstance(value, str):
            has_escaped_character = any(char in value for char in escape_characters)
            if has_escaped_character:
                for char in escape_characters:
                    value = value.replace(char, f"\\{char}")
            value = f"%{value}%"

        if hasattr(value, "pk"):
            value = value.pk

        if op in {"isnull", "isempty"} and field_obj is not None:
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
    """
    Creates a SQLAlchemy OR clause for the expressions being passed.
    """
    return sqlalchemy.or_(*args, **kwargs)


def and_(*args: Any, **kwargs: Any) -> Any:
    """
    Creates a SQLAlchemy AND clause for the expressions being passed.
    """
    return sqlalchemy.and_(*args, **kwargs)


def not_(*args: Any, **kwargs: Any) -> Any:
    """
    Creates a SQLAlchemy NOT clause for the expressions being passed.
    """
    return sqlalchemy.not_(*args, **kwargs)
