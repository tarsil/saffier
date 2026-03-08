import copy
import warnings
from collections.abc import AsyncIterator, Generator, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    cast,
)

import sqlalchemy

import saffier
from saffier.core.db import fields as saffier_fields
from saffier.core.db.context_vars import get_schema
from saffier.core.db.datastructures import QueryModelResultCache
from saffier.core.db.fields import CharField, TextField
from saffier.core.db.querysets.clauses import Q, build_lookup_clauses
from saffier.core.db.querysets.mixins import QuerySetPropsMixin, SaffierModel, TenancyMixin
from saffier.core.db.querysets.prefetch import PrefetchMixin
from saffier.core.db.querysets.protocols import AwaitableQuery
from saffier.core.utils.db import check_db_connection, hash_tablekey
from saffier.core.utils.models import DateParser
from saffier.core.utils.schemas import Schema
from saffier.exceptions import MultipleObjectsReturned, ObjectNotFound, QuerySetError
from saffier.protocols.queryset import QuerySetProtocol

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Database
    from saffier.core.db.models.model import Model, ReflectModel


class BaseQuerySet(
    TenancyMixin, QuerySetPropsMixin, PrefetchMixin, DateParser, AwaitableQuery[SaffierModel]
):
    ESCAPE_CHARACTERS = ["%", "_"]

    def __init__(
        self,
        model_class: type["Model"] | None = None,
        database: Union["Database", None] = None,
        filter_clauses: Any = None,
        or_clauses: Any = None,
        select_related: Any = None,
        filter_related: Any = None,
        prefetch_related: Any = None,
        limit_count: Any = None,
        limit_offset: Any = None,
        order_by: Any = None,
        group_by: Any = None,
        distinct_on: Any = None,
        only_fields: Any = None,
        defer_fields: Any = None,
        m2m_related: Any = None,
        using_schema: Any = None,
        table: Any = None,
        exclude_secrets: Any = False,
        for_update: Any = None,
        batch_size: int | None = None,
        extra_select: Any = None,
        reference_select: Any = None,
        embed_parent: Any = None,
    ) -> None:
        super().__init__(model_class=model_class)
        self.model_class = cast("type[Model]", model_class)
        self.filter_clauses = [] if filter_clauses is None else filter_clauses
        self.or_clauses = [] if or_clauses is None else or_clauses
        self.limit_count = limit_count
        self._select_related = [] if select_related is None else select_related
        self._filter_related = [] if filter_related is None else filter_related
        self._prefetch_related = [] if prefetch_related is None else prefetch_related
        self._offset = limit_offset
        self._order_by = [] if order_by is None else order_by
        self._group_by = [] if group_by is None else group_by
        self.distinct_on = distinct_on
        self._only = [] if only_fields is None else only_fields
        self._defer = [] if defer_fields is None else defer_fields
        self._expression = None
        cache_attrs = tuple(getattr(self.model_class, "pkcolumns", ())) if model_class else ()
        self._cache = QueryModelResultCache(attrs=cache_attrs)
        self._cached_select_with_tables = None
        self._cached_select_related_expression = None
        self._source_queryset = self
        self._m2m_related = m2m_related  # type: ignore
        self.using_schema = using_schema
        self._exclude_secrets = exclude_secrets or False
        self.extra: dict[str, Any] = {}
        self._for_update = for_update
        self._batch_size = batch_size
        self._extra_select = [] if extra_select is None else extra_select
        self._reference_select = {} if reference_select is None else reference_select
        self.embed_parent = embed_parent
        self.embed_parent_filters = None

        if self.is_m2m and not self._m2m_related:
            self._m2m_related = self.model_class.meta.multi_related[0]

        if table is not None:
            self.table = table
        if database is not None:
            self.database = database

        self._clear_cache(keep_result_cache=False)

    @property
    def _has_dynamic_clauses(self) -> bool:
        return any(callable(clause) for clause in (*self.filter_clauses, *self.or_clauses))

    def _clear_cache(
        self,
        *,
        keep_result_cache: bool = False,
        keep_cached_selected: bool = False,
    ) -> None:
        if not keep_result_cache:
            self._cache.clear()
        if not keep_cached_selected:
            self._cached_select_with_tables = None
        self._cache_count: int | None = None
        self._cache_first: SaffierModel | None = None
        self._cache_last: SaffierModel | None = None
        self._cache_fetch_all = False

    def _cache_or_return_result(self, result: SaffierModel) -> SaffierModel:
        cached = self._cache.get(self.model_class, result)
        if cached is not None:
            return cast("SaffierModel", cached)
        self._cache.update(self.model_class, [result])
        return result

    def _build_order_by_expression(
        self,
        order_by: Any,
        expression: Any,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        """Builds the order by expression"""
        order_by = [self._prepare_order_by(value, tables_and_models) for value in order_by]
        expression = expression.order_by(*order_by)
        return expression

    def _build_group_by_expression(
        self,
        group_by: Any,
        expression: Any,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        """Builds the group by expression"""
        group_by = [self._prepare_group_by(value, tables_and_models) for value in group_by]
        expression = expression.group_by(*group_by)
        return expression

    def _build_filter_clauses_expression(self, filter_clauses: Any, expression: Any) -> Any:
        """Builds the filter clauses expression"""
        if len(filter_clauses) == 1:
            clause = filter_clauses[0]
        else:
            clause = sqlalchemy.sql.and_(*filter_clauses)
        expression = expression.where(clause)
        return expression

    def _build_or_clauses_expression(self, or_clauses: Any, expression: Any) -> Any:
        """Builds the filter clauses expression"""
        clause = or_clauses[0] if len(or_clauses) == 1 else sqlalchemy.sql.or_(*or_clauses)
        expression = expression.where(clause)
        return expression

    def _build_select_distinct(
        self,
        distinct_on: Any,
        expression: Any,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        """Filters selects only specific fields"""
        if not distinct_on:
            expression = expression.distinct()
        else:
            distinct_on = [
                self._prepare_fields_for_distinct(value, tables_and_models)
                for value in distinct_on
            ]
            expression = expression.distinct(*distinct_on)
        return expression

    def _is_multiple_foreign_key(
        self, model_class: type["Model"] | type["ReflectModel"]
    ) -> tuple[bool, list[tuple[str, str, str]]]:
        """
        Checks if the table has multiple foreign keys to the same table.
        Iterates through all fields of type ForeignKey and OneToOneField and checks if there are
        multiple FKs to the same destination table.

        Returns a tuple of bool, list of tuples
        """
        fields = model_class.fields  # type: ignore
        foreign_keys = []
        has_many = False

        counter = 0

        for key, value in fields.items():
            tablename = None

            if counter > 1:
                has_many = True

            if isinstance(value, (saffier.ForeignKey, saffier.OneToOneField)):
                tablename = value.to if isinstance(value.to, str) else value.to.__name__

                if tablename not in foreign_keys:
                    foreign_keys.append((key, tablename, value.related_name))
                    counter += 1
                else:
                    counter += 1

        return has_many, foreign_keys  # type: ignore

    def _resolve_many_to_many_join_fields(
        self,
        previous_model_class: type["Model"] | type["ReflectModel"],
        related_field: saffier_fields.ManyToManyField,
    ) -> tuple[type["Model"] | type["ReflectModel"], str, str]:
        through_model = related_field.through
        if isinstance(through_model, str):
            registry = getattr(previous_model_class.meta, "registry", None)
            if registry is not None:
                through_model = registry.models.get(through_model) or registry.reflected.get(
                    through_model
                )
                related_field.through = through_model

        if through_model is None or isinstance(through_model, str):
            raise QuerySetError(
                detail=(
                    "Unable to resolve through model for select_related path "
                    f"'{previous_model_class.__name__}.{related_field.name}'."
                )
            )

        from_field: str | None = None
        to_field: str | None = None
        for field_name, field in through_model.fields.items():
            if not isinstance(field, (saffier_fields.ForeignKey, saffier_fields.OneToOneField)):
                continue
            if field.target is previous_model_class and from_field is None:
                from_field = field_name
                continue
            if field.target is related_field.target and to_field is None:
                to_field = field_name

        if from_field is None or to_field is None:
            raise QuerySetError(
                detail=(
                    "Unable to resolve many-to-many join fields for "
                    f"'{previous_model_class.__name__}.{related_field.name}'."
                )
            )

        return cast("type[Model] | type[ReflectModel]", through_model), from_field, to_field

    @staticmethod
    def _primary_join_columns(
        table: Any, model_class: type["Model"] | type["ReflectModel"]
    ) -> list[Any]:
        columns = [
            getattr(table.c, pk_name, None) for pk_name in getattr(model_class, "pkcolumns", ())
        ]
        resolved = [column for column in columns if column is not None]
        if resolved:
            return resolved
        return list(table.primary_key)

    @staticmethod
    def _relation_join_columns(table: Any, field_name: str, field: Any) -> list[Any]:
        column_names = (
            field.get_column_names(field_name)
            if hasattr(field, "get_column_names")
            else (field_name,)
        )
        return [getattr(table.c, column_name, None) for column_name in column_names]

    @staticmethod
    def _target_relation_columns(table: Any, field: Any) -> list[Any]:
        related_columns = getattr(field, "related_columns", {})
        return [getattr(table.c, column_name, None) for column_name in related_columns]

    @staticmethod
    def _build_join_condition(left_columns: Sequence[Any], right_columns: Sequence[Any]) -> Any:
        pairs = [
            (left_column, right_column)
            for left_column, right_column in zip(left_columns, right_columns, strict=False)
            if left_column is not None and right_column is not None
        ]
        if not pairs or len(pairs) != len(left_columns) or len(pairs) != len(right_columns):
            raise QuerySetError(detail="Unable to resolve join columns for relationship.")
        clauses = [left_column == right_column for left_column, right_column in pairs]
        if len(clauses) == 1:
            return clauses[0]
        return sqlalchemy.and_(*clauses)

    def _dedupe_related_paths(self, paths: Sequence[str]) -> list[str]:
        related_paths = list(dict.fromkeys(path for path in paths if path))
        return [
            path
            for path in related_paths
            if not any(other != path and other.startswith(f"{path}__") for other in related_paths)
        ]

    def _collect_related_paths(self, fields: Sequence[str]) -> list[str]:
        from saffier.core.db.relationships.utils import crawl_relationship

        related_paths: list[str] = []
        for value in fields:
            if not isinstance(value, str):
                continue
            crawl_result = crawl_relationship(
                self.model_class,
                value.lstrip("-"),
                model_database=self.database,
            )
            if crawl_result.forward_path:
                related_paths.append(crawl_result.forward_path)
        return self._dedupe_related_paths(related_paths)

    def _build_tables_select_from_relationship(
        self,
        related_paths: Sequence[str] | None = None,
    ) -> Any:
        """
        Builds the tables relationships and joins.
        When a table contains more than one foreign key pointing to the same
        destination table, a lookup for the related field is made to understand
        from which foreign key the table is looked up from.
        """
        queryset: QuerySet = self._clone()

        tables = [queryset.table]
        select_from = queryset.table
        tables_and_models: dict[str, tuple[Any, Any]] = {
            "": (queryset.table, queryset.model_class)
        }

        select_related = self._dedupe_related_paths(
            queryset._select_related if related_paths is None else related_paths
        )

        # Select related
        for item in select_related:
            # For m2m relationships
            model_class = queryset.model_class
            current_table = queryset.table
            prefix = ""

            for part in item.split("__"):
                has_many_fk_same_table = False
                keys: list[tuple[str, str, str]] = []
                previous_model_class = model_class
                previous_table = current_table
                join_lookup_field: str | None = None
                reverse_join = False
                current_related_field: Any = None
                through_model: Any = None
                through_table = None
                through_from_field: str | None = None
                through_to_field: str | None = None
                try:
                    current_related_field = model_class.fields[part]
                    model_class = current_related_field.target
                    if isinstance(
                        current_related_field,
                        (saffier_fields.ForeignKey, saffier_fields.OneToOneField),
                    ):
                        join_lookup_field = part
                    elif isinstance(current_related_field, saffier_fields.ManyToManyField):
                        through_model, through_from_field, through_to_field = (
                            self._resolve_many_to_many_join_fields(
                                previous_model_class,
                                current_related_field,
                            )
                        )
                        through_table = (
                            through_model.table_schema(queryset.using_schema)
                            if queryset.using_schema is not None
                            else through_model.table
                        )
                except (KeyError, AttributeError):
                    # Check related fields
                    model_class = getattr(model_class, part).related_from
                    reverse_join = True
                    join_lookup_field = previous_model_class.meta.related_names_mapping.get(part)
                    has_many_fk_same_table, keys = self._is_multiple_foreign_key(model_class)

                next_prefix = part if not prefix else f"{prefix}__{part}"

                if queryset.using_schema is not None:
                    table = model_class.table_schema(queryset.using_schema)
                else:
                    table = model_class.table
                if model_class is previous_model_class or next_prefix in tables_and_models:
                    table = table.alias(
                        hash_tablekey(tablekey=model_class.meta.tablename, prefix=next_prefix)
                    )

                if isinstance(current_related_field, saffier_fields.ManyToManyField):
                    assert through_table is not None
                    assert through_model is not None
                    through_from_relation = through_model.fields[through_from_field]
                    through_to_relation = through_model.fields[through_to_field]
                    through_prefix = f"{next_prefix}__through"
                    if (
                        through_model is previous_model_class
                        or through_prefix in tables_and_models
                    ):
                        through_table = through_table.alias(
                            hash_tablekey(
                                tablekey=through_model.meta.tablename,
                                prefix=through_prefix,
                            )
                        )
                    left_columns = self._primary_join_columns(previous_table, previous_model_class)
                    through_left_columns = self._relation_join_columns(
                        through_table,
                        through_from_field,
                        through_from_relation,
                    )
                    through_right_columns = self._relation_join_columns(
                        through_table,
                        through_to_field,
                        through_to_relation,
                    )
                    right_columns = self._primary_join_columns(table, model_class)
                    select_from = sqlalchemy.sql.join(
                        select_from,
                        through_table,
                        self._build_join_condition(left_columns, through_left_columns),
                    )
                    select_from = sqlalchemy.sql.join(
                        select_from,
                        table,
                        self._build_join_condition(through_right_columns, right_columns),
                    )
                    prefix = next_prefix
                    tables_and_models[prefix] = (table, model_class)
                    current_table = table
                    tables.append(table)
                    continue

                # If there is multiple FKs to the same table
                if not has_many_fk_same_table:
                    if join_lookup_field is not None:
                        if reverse_join:
                            relation_field = model_class.fields[join_lookup_field]
                            left_columns = self._target_relation_columns(
                                previous_table,
                                relation_field,
                            )
                            right_columns = self._relation_join_columns(
                                table,
                                join_lookup_field,
                                relation_field,
                            )
                        else:
                            relation_field = current_related_field
                            left_columns = self._relation_join_columns(
                                previous_table,
                                join_lookup_field,
                                relation_field,
                            )
                            right_columns = self._target_relation_columns(table, relation_field)

                        select_from = sqlalchemy.sql.join(
                            select_from,
                            table,
                            self._build_join_condition(left_columns, right_columns),
                        )
                    else:
                        select_from = sqlalchemy.sql.join(select_from, table)
                else:
                    lookup_field = None

                    # Extract the table field from the related
                    # Assign to a lookup_field
                    for values in keys:
                        field, _, related_name = values
                        if related_name == part:
                            lookup_field = field
                            break

                    if lookup_field is None:
                        select_from = sqlalchemy.sql.join(select_from, table)
                    else:
                        relation_field = model_class.fields[lookup_field]
                        left_columns = self._target_relation_columns(
                            previous_table, relation_field
                        )
                        right_columns = self._relation_join_columns(
                            table,
                            lookup_field,
                            relation_field,
                        )
                        select_from = sqlalchemy.sql.join(
                            select_from,
                            table,
                            self._build_join_condition(left_columns, right_columns),
                        )

                prefix = next_prefix
                tables_and_models[prefix] = (table, model_class)
                current_table = table
                tables.append(table)
        return tables, select_from, tables_and_models

    def _should_include_selected_column(
        self,
        field_name: str,
        model_class: Any,
        prefix: str = "",
    ) -> bool:
        if self._only:
            if not prefix and field_name not in self._only:
                return False
            if prefix and prefix not in self._only and f"{prefix}__{field_name}" not in self._only:
                return False

        if self._defer:
            if not prefix and field_name in self._defer:
                return False
            if prefix and (prefix in self._defer or f"{prefix}__{field_name}" in self._defer):
                return False

        return not (
            self._exclude_secrets
            and field_name in model_class.meta.fields
            and model_class.meta.fields[field_name].secret
        )

    def _build_select_columns(
        self,
        tables_and_models: dict[str, tuple[Any, Any]],
        selectable_related: set[str],
    ) -> list[Any]:
        columns: list[Any] = [*self._extra_select]

        for prefix, (table, model_class) in tables_and_models.items():
            if prefix and not any(
                related_path == prefix or related_path.startswith(f"{prefix}__")
                for related_path in selectable_related
            ):
                continue

            for column_key, column in table.columns.items():
                field_name = model_class.meta.columns_to_field.get(column_key, column_key)
                if not self._should_include_selected_column(field_name, model_class, prefix):
                    continue

                columns.append(column)

        if not columns:
            raise QuerySetError("No columns selected for queryset.")
        return columns

    def _build_where_clause(
        self,
        outer_tables_and_models: dict[str, tuple[Any, Any]],
        outer_select_paths: Sequence[str],
    ) -> Any:
        where_clauses: list[Any] = []
        if self.or_clauses:
            clause = (
                self.or_clauses[0]
                if len(self.or_clauses) == 1
                else sqlalchemy.sql.or_(*self.or_clauses)
            )
            where_clauses.append(clause)
        if self.filter_clauses:
            where_clauses.extend(self.filter_clauses)
        if not where_clauses:
            return None

        full_select_paths = self._dedupe_related_paths(
            [*outer_select_paths, *self._filter_related]
        )
        _, full_select_from, full_tables_and_models = self._build_tables_select_from_relationship(
            full_select_paths
        )

        if len(full_tables_and_models) == 1:
            return (
                where_clauses[0]
                if len(where_clauses) == 1
                else sqlalchemy.sql.and_(*where_clauses)
            )

        outer_table, outer_model = outer_tables_and_models[""]
        pk_columns = [getattr(outer_table.c, column) for column in outer_model.pkcolumns]
        subquery = (
            sqlalchemy.select(*pk_columns).select_from(full_select_from).where(*where_clauses)
        )

        if len(pk_columns) == 1:
            return pk_columns[0].in_(subquery)
        return sqlalchemy.tuple_(*pk_columns).in_(subquery)

    def _validate_only_and_defer(self) -> None:
        if self._only and self._defer:
            raise QuerySetError("You cannot use .only() and .defer() at the same time.")

    def _secret_recursive_names(
        self, model_class: Any, columns: list[str] | None = None
    ) -> list[str]:
        """
        Recursively gets the names of the fields excluding the secrets.
        """
        if columns is None:
            columns = []

        for name, field in model_class.fields.items():
            if isinstance(field, saffier_fields.ForeignKey):
                # Making sure the foreign key is always added unless is a secret
                if not field.secret:
                    columns.append(name)
                    columns.extend(
                        self._secret_recursive_names(model_class=field.target, columns=columns)
                    )
                continue
            if not field.secret:
                columns.append(name)

        columns = list(set(columns))
        return columns

    def _build_select_with_tables(self) -> tuple[Any, dict[str, tuple[Any, Any]]]:
        """
        Builds the query select based on the given parameters and filters.
        """
        if self._cached_select_with_tables is not None:
            return self._cached_select_with_tables

        queryset = self

        queryset._validate_only_and_defer()
        outer_select_paths = queryset._dedupe_related_paths(
            [
                *queryset._select_related,
                *queryset._collect_related_paths(queryset._order_by),
                *queryset._collect_related_paths(queryset._group_by),
            ]
        )
        _, select_from, tables_and_models = queryset._build_tables_select_from_relationship(
            outer_select_paths
        )
        selectable_related = set(queryset._select_related)
        columns = queryset._build_select_columns(tables_and_models, selectable_related)
        expression = sqlalchemy.sql.select(*columns).select_from(select_from)

        where_clause = queryset._build_where_clause(tables_and_models, outer_select_paths)
        if where_clause is not None:
            expression = expression.where(where_clause)

        if queryset._order_by:
            expression = queryset._build_order_by_expression(
                queryset._order_by,
                expression=expression,
                tables_and_models=tables_and_models,
            )

        if queryset.limit_count:
            expression = expression.limit(queryset.limit_count)

        if queryset._offset:
            expression = expression.offset(queryset._offset)

        if queryset._group_by:
            expression = queryset._build_group_by_expression(
                queryset._group_by,
                expression=expression,
                tables_and_models=tables_and_models,
            )

        if queryset.distinct_on is not None:
            expression = queryset._build_select_distinct(
                queryset.distinct_on,
                expression=expression,
                tables_and_models=tables_and_models,
            )

        if queryset._for_update:
            for_update = dict(queryset._for_update)
            of = for_update.get("of")
            if of:
                for_update["of"] = tuple(
                    getattr(model, "table", model) for model in cast("tuple[Any, ...]", of)
                )
            expression = expression.with_for_update(**for_update)

        queryset._expression = expression  # type: ignore
        if queryset._select_related:
            queryset._cached_select_related_expression = expression
            queryset._source_queryset._cached_select_related_expression = expression
        queryset._cached_select_with_tables = (expression, tables_and_models)
        return queryset._cached_select_with_tables

    def _build_select(self) -> Any:
        return self._build_select_with_tables()[0]

    async def _hydrate_row(
        self,
        queryset: "QuerySet",
        row: Any,
        tables_and_models: dict[str, tuple[Any, Any]],
        *,
        is_only_fields: bool,
        is_defer_fields: bool,
    ) -> SaffierModel:
        result = queryset.model_class.from_query_result(
            row,
            select_related=queryset._select_related,
            prefetch_related=[],
            is_only_fields=is_only_fields,
            only_fields=queryset._only,
            is_defer_fields=is_defer_fields,
            using_schema=queryset.using_schema,
            exclude_secrets=queryset._exclude_secrets,
            reference_select=queryset._reference_select,
            tables_and_models=tables_and_models,
        )
        if queryset._prefetch_related:
            result = await queryset.model_class.apply_prefetch_related(
                row=row,
                model=result,
                prefetch_related=queryset._prefetch_related,
            )
        return result

    def _filter_query(self, exclude: bool = False, or_: bool = False, **kwargs: Any) -> "QuerySet":
        clauses: list[Any] = []
        filter_clauses = self.filter_clauses
        or_clauses = self.or_clauses
        select_related = list(self._select_related)
        filter_related = list(self._filter_related)
        prefetch_related = list(self._prefetch_related)

        # Making sure for queries we use the main class and not the proxy
        # And enable the parent
        if self.model_class.is_proxy_model:
            self.model_class = self.model_class.parent

        clauses, implied_select_related = build_lookup_clauses(
            self.model_class,
            self.table,
            kwargs,
            escape_characters=tuple(self.ESCAPE_CHARACTERS),
            using_schema=self.using_schema,
            embed_parent=self.embed_parent_filters,
            model_database=self.database,
        )
        for related_path in implied_select_related:
            if related_path not in filter_related:
                filter_related.append(related_path)

        if exclude:
            if clauses:
                if not or_:
                    filter_clauses.append(sqlalchemy.not_(sqlalchemy.sql.and_(*clauses)))
                else:
                    or_clauses.append(sqlalchemy.not_(sqlalchemy.sql.and_(*clauses)))
        else:
            if not or_:
                filter_clauses += clauses
            else:
                or_clauses += clauses

        return cast(
            "QuerySet",
            self.__class__(
                model_class=self.model_class,
                database=self._database,
                filter_clauses=filter_clauses,
                or_clauses=or_clauses,
                select_related=select_related,
                filter_related=filter_related,
                prefetch_related=prefetch_related,
                limit_count=self.limit_count,
                limit_offset=self._offset,
                order_by=self._order_by,
                only_fields=self._only,
                defer_fields=self._defer,
                m2m_related=self.m2m_related,
                exclude_secrets=self._exclude_secrets,
                table=self.table,
                using_schema=self.using_schema,
                for_update=self._for_update,
                batch_size=self._batch_size,
                extra_select=self._extra_select,
                reference_select=self._reference_select,
                embed_parent=self.embed_parent,
            ),
        )

    def _validate_kwargs(self, **kwargs: Any) -> Any:
        original_kwargs = dict(kwargs)
        fields = self.model_class.fields
        for key, field in fields.items():
            field.modify_input(key, kwargs)
        schema_fields = {}
        for key, value in fields.items():
            if not value.has_column():
                continue
            field_validator = value.validator
            if key in kwargs and field_validator.read_only:
                field_validator = copy.copy(field_validator)
                field_validator.read_only = False
            schema_fields[key] = field_validator
        validator = Schema(fields=schema_fields)
        kwargs = validator.check(kwargs)
        for key, value in original_kwargs.items():
            field = fields.get(key)
            if field is not None and not field.has_column():
                kwargs[key] = value
        for key, value in fields.items():
            if not value.has_column():
                continue
            if value.validator.read_only and value.validator.has_default():
                kwargs[key] = value.validator.get_default_value()
        return kwargs

    def _normalize_many_to_many_values(
        self,
        field: saffier_fields.ManyToManyField,
        value: Any,
    ) -> list[Any]:
        if value is None:
            return []

        values: Sequence[Any]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values = value
        else:
            values = [value]

        target = field.target
        normalized = []
        for item in values:
            if item is None:
                continue
            if isinstance(item, target):
                normalized.append(item)
            else:
                normalized.append(target(pk=item))
        return normalized

    def _prepare_order_by(
        self,
        order_by: str,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        from saffier.core.db.relationships.utils import crawl_relationship

        reverse = order_by.startswith("-")
        order_by = order_by.lstrip("-")
        crawl_result = crawl_relationship(
            self.model_class,
            order_by,
            model_database=self.database,
        )
        table = tables_and_models[crawl_result.forward_path][0]
        order_col = table.columns[crawl_result.field_name]
        return order_col.desc() if reverse else order_col

    def _prepare_group_by(
        self,
        group_by: str,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        from saffier.core.db.relationships.utils import crawl_relationship

        group_by = group_by.lstrip("-")
        crawl_result = crawl_relationship(
            self.model_class,
            group_by,
            model_database=self.database,
        )
        table = tables_and_models[crawl_result.forward_path][0]
        group_col = table.columns[crawl_result.field_name]
        return group_col

    def _prepare_fields_for_distinct(
        self,
        distinct_on: str,
        tables_and_models: dict[str, tuple[Any, Any]],
    ) -> Any:
        from saffier.core.db.relationships.utils import crawl_relationship

        crawl_result = crawl_relationship(
            self.model_class,
            distinct_on,
            model_database=self.database,
        )
        table = tables_and_models[crawl_result.forward_path][0]
        _distinct_on: sqlalchemy.Column = table.columns[crawl_result.field_name]
        return _distinct_on

    def _clone(self) -> Any:
        """
        Return a copy of the current QuerySet that's ready for another
        operation.
        """
        queryset = self.__class__.__new__(self.__class__)
        queryset.model_class = self.model_class

        # Making sure the registry schema takes precendent with
        # Any provided using
        effective_schema = self.using_schema
        if not self.model_class.meta.registry.db_schema:
            schema = get_schema()
            if effective_schema is None and schema is not None:
                effective_schema = schema

        queryset.filter_clauses = copy.copy(self.filter_clauses)
        queryset.or_clauses = copy.copy(self.or_clauses)
        queryset.limit_count = self.limit_count
        queryset._select_related = copy.copy(self._select_related)
        queryset._filter_related = copy.copy(self._filter_related)
        queryset._prefetch_related = copy.copy(self._prefetch_related)
        queryset._offset = self._offset
        queryset._order_by = copy.copy(self._order_by)
        queryset._group_by = copy.copy(self._group_by)
        queryset.distinct_on = copy.copy(self.distinct_on)
        queryset._expression = self._expression
        queryset._cache = QueryModelResultCache(attrs=self._cache.attrs, prefix=self._cache.prefix)
        queryset._cached_select_with_tables = None
        queryset._cached_select_related_expression = self._cached_select_related_expression
        queryset._source_queryset = getattr(self, "_source_queryset", self)
        queryset._m2m_related = self._m2m_related
        queryset._only = copy.copy(self._only)
        queryset._defer = copy.copy(self._defer)
        queryset._database = self.database
        if effective_schema is not None:
            queryset.table = self.model_class.table_schema(effective_schema)
        elif getattr(self.model_class, "_table", None) is None:
            queryset.table = self.model_class.table
        else:
            queryset.table = self.table
        queryset.extra = copy.copy(self.extra)
        queryset._exclude_secrets = self._exclude_secrets
        queryset.using_schema = effective_schema
        queryset._for_update = copy.copy(self._for_update)
        queryset._batch_size = self._batch_size
        queryset._extra_select = copy.copy(self._extra_select)
        queryset._reference_select = copy.copy(self._reference_select)
        queryset.embed_parent = self.embed_parent
        queryset.embed_parent_filters = self.embed_parent_filters
        queryset._cache_count = None
        queryset._cache_first = None
        queryset._cache_last = None
        queryset._cache_fetch_all = False

        return queryset


class QuerySet(BaseQuerySet, QuerySetProtocol):
    """
    QuerySet object used for query retrieving.
    """

    def __get__(self, instance: Any, owner: Any) -> "QuerySet":
        return self.__class__(model_class=owner)

    @property
    def sql(self) -> str:
        if self._expression is None:
            self._expression = self._build_select()
        database = getattr(self, "_database", None)
        try:
            engine = getattr(database, "engine", None)
        except RuntimeError:
            engine = None
        if engine is None:
            return str(self._expression)
        try:
            compiled = self._expression.compile(engine, compile_kwargs={"literal_binds": True})
        except Exception:
            return str(self._expression)
        return str(compiled)

    @sql.setter
    def sql(self, value: Any) -> None:
        self._expression = value

    async def __aiter__(self) -> AsyncIterator[SaffierModel]:
        async for value in self._execute_iterate():
            yield value

    def _set_query_expression(self, expression: Any) -> None:
        """
        Sets the value of the sql property to the expression used.
        """
        self.sql = expression
        self.model_class.raw_query = self.sql

    def _filter_or_exclude(
        self,
        clause: Any = None,
        exclude: bool = False,
        or_: bool = False,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters or excludes a given clause for a specific QuerySet.
        """
        queryset: QuerySet = self._clone()

        if clause is None:
            return queryset._filter_query(exclude=exclude, or_=or_, **kwargs)

        if kwargs:
            queryset = queryset._filter_query(exclude=exclude, or_=or_, **kwargs)

        if isinstance(clause, Q):
            clause, implied_select_related = clause.resolve(queryset)
            for related_path in implied_select_related:
                if related_path not in queryset._filter_related:
                    queryset._filter_related.append(related_path)

        if exclude and isinstance(clause, Q):
            clause = sqlalchemy.not_(clause)

        if or_:
            queryset.or_clauses.append(clause)
        else:
            queryset.filter_clauses.append(clause)

        return queryset

    def filter(
        self,
        clause: Any = None,
        or_: bool = False,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the given kwargs and clause.
        """
        return self._filter_or_exclude(clause=clause, or_=or_, **kwargs)

    def or_(
        self,
        clause: Any = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the OR operand.
        """
        queryset: QuerySet = self._clone()
        queryset = self.filter(clause=clause, or_=True, **kwargs)
        return queryset

    def local_or(
        self,
        clause: Any = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Local OR alias matching the Saffier queryset style.
        """
        queryset: QuerySet = self._clone()
        queryset = self.filter(clause=clause, or_=True, **kwargs)
        return queryset

    def and_(
        self,
        clause: Any = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the AND operand.
        """
        queryset: QuerySet = self._clone()
        queryset = self.filter(clause=clause, **kwargs)
        return queryset

    def not_(
        self,
        clause: Any = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the NOT operand.
        """
        queryset: QuerySet = self._clone()
        queryset = queryset.exclude(clause=clause, **kwargs)
        return queryset

    def exclude(
        self,
        clause: Any = None,
        or_: bool = False,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Exactly the same as the filter but for the exclude.
        """
        queryset: QuerySet = self._clone()
        queryset = self._filter_or_exclude(clause=clause, exclude=True, or_=or_, **kwargs)
        return queryset

    def exclude_secrets(
        self,
        enabled: bool = True,
        clause: Any = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Excludes any field that contains the `secret=True` declared from being leaked.
        """
        queryset: QuerySet = self._clone()
        queryset._exclude_secrets = enabled
        queryset = queryset.filter(clause=clause, **kwargs)
        return queryset

    def lookup(self, term: Any) -> "QuerySet":
        """
        Broader way of searching for a given term
        """
        queryset: QuerySet = self._clone()
        if not term:
            return queryset

        filter_clauses = list(queryset.filter_clauses)
        value = f"%{term}%"

        search_fields = [
            name
            for name, field in queryset.model_class.fields.items()
            if isinstance(field, (CharField, TextField))
        ]
        search_clauses = [queryset.table.columns[name].ilike(value) for name in search_fields]

        if len(search_clauses) > 1:
            filter_clauses.append(sqlalchemy.sql.or_(*search_clauses))
        else:
            filter_clauses.extend(search_clauses)

        return queryset

    def order_by(self, *order_by: str) -> "QuerySet":
        """
        Returns a QuerySet ordered by the given fields.
        """
        queryset: QuerySet = self._clone()
        queryset._order_by = order_by
        return queryset

    def reverse(self) -> "QuerySet":
        """
        Reverses the established order of the QuerySet.
        """
        queryset: QuerySet = self._clone()
        if not queryset._order_by:
            queryset = queryset.order_by(*queryset.model_class.pknames)

        queryset._order_by = tuple(
            value[1:] if value.startswith("-") else f"-{value}" for value in queryset._order_by
        )
        queryset._cache_first = self._cache_last
        queryset._cache_last = self._cache_first
        queryset._cache_count = self._cache_count
        if self._cache_fetch_all:
            values = list(reversed(tuple(self._cache.get_category(self.model_class).values())))
            queryset._cache.update(queryset.model_class, values)
            queryset._cache_fetch_all = True
        return queryset

    def batch_size(self, batch_size: int | None = None) -> "QuerySet":
        """
        Sets the chunk size for async queryset iteration.
        """
        queryset: QuerySet = self._clone()
        queryset._batch_size = batch_size
        return queryset

    def extra_select(self, *extra: Any) -> "QuerySet":
        """
        Adds extra SQLAlchemy expressions to the SELECT list.
        """
        queryset: QuerySet = self._clone()
        queryset._extra_select.extend(extra)
        return queryset

    def reference_select(self, references: dict[str, Any]) -> "QuerySet":
        """
        Adds named reference selections to the SELECT list.
        """
        queryset: QuerySet = self._clone()
        queryset._reference_select.update(references)
        return queryset

    def paginator(
        self,
        page_size: int,
        *,
        next_item_attr: str = "",
        previous_item_attr: str = "",
    ) -> Any:
        """
        Returns a numbered paginator bound to the queryset.
        """
        from saffier.contrib.pagination import NumberedPaginator

        return NumberedPaginator(
            queryset=self._clone(),
            page_size=page_size,
            next_item_attr=next_item_attr,
            previous_item_attr=previous_item_attr,
        )

    def cursor_paginator(
        self,
        page_size: int,
        *,
        next_item_attr: str = "",
        previous_item_attr: str = "",
    ) -> Any:
        """
        Returns a cursor paginator bound to the queryset.
        """
        from saffier.contrib.pagination import CursorPaginator

        return CursorPaginator(
            queryset=self._clone(),
            page_size=page_size,
            next_item_attr=next_item_attr,
            previous_item_attr=previous_item_attr,
        )

    def limit(self, limit_count: int) -> "QuerySet":
        """
        Returns a QuerySet limited by.
        """
        queryset: QuerySet = self._clone()
        queryset.limit_count = limit_count
        return queryset

    def offset(self, offset: int) -> "QuerySet":
        """
        Returns a Queryset limited by the offset.
        """
        queryset: QuerySet = self._clone()
        queryset._offset = offset
        return queryset

    def group_by(self, *group_by: str) -> "QuerySet":
        """
        Returns the values grouped by the given fields.
        """
        queryset: QuerySet = self._clone()
        queryset._group_by = group_by
        return queryset

    def distinct(self, first: bool | str = True, *distinct_on: str) -> "QuerySet":
        """
        Returns a queryset with distinct results.
        """
        queryset: QuerySet = self._clone()
        if first is False:
            queryset.distinct_on = None
        elif first is True:
            queryset.distinct_on = []
        else:
            queryset.distinct_on = [first, *distinct_on]
        return queryset

    def only(self, *fields: Sequence[str]) -> "QuerySet":
        """
        Returns a list of models with the selected only fields and always the primary
        key.
        """
        only_fields = list(fields)
        for pkcolumn in reversed(tuple(self.model_class.pkcolumns)):
            if pkcolumn not in only_fields:
                only_fields.insert(0, pkcolumn)

        queryset: QuerySet = self._clone()
        queryset._only = only_fields
        return queryset

    def defer(self, *fields: Sequence[str]) -> "QuerySet":
        """
        Returns a list of models with the selected only fields and always the primary
        key.
        """
        queryset: QuerySet = self._clone()
        queryset._defer = fields
        return queryset

    def select_related(self, related: Any) -> "QuerySet":
        """
        Returns a QuerySet that will “follow” foreign-key relationships, selecting additional
        related-object data when it executes its query.

        This is a performance booster which results in a single more complex query but means

        later use of foreign-key relationships won’t require database queries.
        """
        queryset: QuerySet = self._clone()
        if not isinstance(related, (list, tuple)):
            related = [related]

        queryset._select_related = queryset._dedupe_related_paths(
            [*queryset._select_related, *related]
        )
        return queryset

    async def values(
        self,
        fields: Sequence[str] | str | None = None,
        exclude: Sequence[str] | set[str] = None,
        exclude_none: bool = False,
        flatten: bool = False,
        **kwargs: Any,
    ) -> list[Any]:
        """
        Returns the results in a python dictionary format.
        """
        fields = fields or []
        queryset: QuerySet = self._clone()
        rows: list[type[Model]] = await queryset.all()

        if not isinstance(fields, list):
            raise QuerySetError(detail="Fields must be an iterable.")

        if not fields:
            rows = [row.model_dump(exclude=exclude, exclude_none=exclude_none) for row in rows]  # type: ignore
        else:
            rows = [
                row.model_dump(exclude=exclude, exclude_none=exclude_none, include=fields)  # type: ignore
                for row in rows
            ]

        as_tuple = kwargs.pop("__as_tuple__", False)

        if not as_tuple:
            return rows

        if not flatten:
            rows = [tuple(row.values()) for row in rows]  # type: ignore
        else:
            try:
                rows = [row[fields[0]] for row in rows]  # type: ignore
            except KeyError:
                raise QuerySetError(detail=f"{fields[0]} does not exist in the results.") from None
        return rows

    async def values_list(
        self,
        fields: Sequence[str] | str | None = None,
        exclude: Sequence[str] | set[str] = None,
        exclude_none: bool = False,
        flat: bool = False,
    ) -> list[Any]:
        """
        Returns the results in a python dictionary format.
        """
        fields = fields or []
        if flat and len(fields) > 1:
            raise QuerySetError(
                detail=f"Maximum of 1 in fields when `flat` is enables, got {len(fields)} instead."
            ) from None

        if flat and isinstance(fields, str):
            fields = [fields]

        if isinstance(fields, str):
            fields = [fields]

        return await self.values(
            fields=fields,
            exclude=exclude,
            exclude_none=exclude_none,
            flatten=flat,
            __as_tuple__=True,
        )

    async def exists(self, **kwargs: Any) -> bool:
        """
        Returns a boolean indicating if a record exists or not.
        """
        if kwargs:
            cached = self._cache.get(self.model_class, kwargs)
            if cached is not None:
                return True
        elif self._cache_count is not None:
            return self._cache_count > 0

        queryset: QuerySet = self.filter(**kwargs) if kwargs else self._clone()
        expression = queryset._build_select()
        expression = sqlalchemy.exists(expression).select()
        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            _exists = await database.fetch_val(expression)
        return cast("bool", _exists)

    async def count(self, **kwargs: Any) -> int:
        """
        Returns an indicating the total records.
        """
        if not kwargs and self._cache_count is not None:
            return self._cache_count

        queryset: QuerySet = self.filter(**kwargs) if kwargs else self._clone()
        base_select = queryset._build_select()
        subquery = base_select.subquery("subquery_for_count")

        needs_distinct = bool(
            queryset.or_clauses
            or queryset._select_related
            or queryset._filter_related
            or queryset._group_by
            or queryset._collect_related_paths(queryset._order_by)
        )
        if needs_distinct:
            pk_columns = [subquery.c[column] for column in queryset.model_class.pkcolumns]
            if len(pk_columns) == 1:
                expression = sqlalchemy.select(
                    sqlalchemy.func.count(sqlalchemy.distinct(pk_columns[0]))
                )
            else:
                expression = sqlalchemy.select(
                    sqlalchemy.func.count(sqlalchemy.distinct(sqlalchemy.tuple_(*pk_columns)))
                )
        else:
            expression = sqlalchemy.select(sqlalchemy.func.count()).select_from(subquery)
        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            _count = await database.fetch_val(expression)
        if not kwargs:
            self._cache_count = cast("int", _count)
        return cast("int", _count)

    async def get_or_none(self, **kwargs: Any) -> SaffierModel | None:
        """
        Fetch one object matching the parameters or returns None.
        """
        try:
            return await self.get(**kwargs)
        except ObjectNotFound:
            return None

    async def _all(self, **kwargs: Any) -> list[SaffierModel]:
        """
        Returns the queryset records based on specific filters
        """
        if kwargs:
            queryset = self.filter(**kwargs)
            queryset._cache = self._cache
            return await queryset._all()

        if self._cache_fetch_all:
            return list(self._cache.get_category(self.model_class).values())

        queryset = self
        if queryset.is_m2m:
            queryset = queryset.distinct(queryset.m2m_related)

        expression, tables_and_models = queryset._build_select_with_tables()
        queryset._set_query_expression(expression)
        self._set_query_expression(expression)
        if queryset._select_related:
            self._cached_select_related_expression = expression

        check_db_connection(queryset.database)
        async with queryset.database as database:
            rows = await database.fetch_all(expression)

        is_only_fields = bool(queryset._only)
        is_defer_fields = bool(queryset._defer)

        # Attach the raw query to the object
        queryset.model_class.raw_query = queryset.sql

        results: list[SaffierModel] = []
        for row in rows:
            result = await queryset._hydrate_row(
                queryset,
                row,
                tables_and_models,
                is_only_fields=is_only_fields,
                is_defer_fields=is_defer_fields,
            )
            if not queryset.is_m2m:
                results.append(
                    queryset._cache_or_return_result(queryset._embed_parent_in_result(result))
                )
            else:
                related_result = getattr(result, queryset.m2m_related)
                results.append(queryset._cache_or_return_result(related_result))

        queryset._cache_count = len(results)
        queryset._cache_first = results[0] if results else None
        queryset._cache_last = results[-1] if results else None
        queryset._cache_fetch_all = True

        return results

    def all(self, clear_cache: bool = False, **kwargs: Any) -> "QuerySet":
        """
        Returns the queryset records based on specific filters
        """
        if clear_cache:
            self._clear_cache(keep_cached_selected=not self._has_dynamic_clauses)
            return self
        queryset: QuerySet = self._clone()
        queryset.extra = kwargs
        return queryset

    async def get(self, **kwargs: Any) -> SaffierModel:
        """
        Returns a single record based on the given kwargs.
        """
        if kwargs:
            cached = self._cache.get(self.model_class, kwargs)
            if cached is not None:
                return cast("SaffierModel", cached)
            queryset = self.filter(**kwargs)
            queryset._cache = self._cache
            return await queryset.get()

        if self._cache_count == 1 and self._cache_first is not None:
            return self._cache_first
        if self._cache_count == 0:
            raise ObjectNotFound()
        if self._cache_fetch_all and self._cache_count and self._cache_count > 1:
            raise MultipleObjectsReturned()

        queryset = self

        expression, tables_and_models = queryset._build_select_with_tables()
        expression = expression.limit(2)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            rows = await database.fetch_all(expression)
        queryset._set_query_expression(expression)
        if queryset._select_related:
            self._cached_select_related_expression = expression

        is_only_fields = bool(queryset._only)
        is_defer_fields = bool(queryset._defer)

        if not rows:
            raise ObjectNotFound()
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        result = await queryset._hydrate_row(
            queryset,
            rows[0],
            tables_and_models,
            is_only_fields=is_only_fields,
            is_defer_fields=is_defer_fields,
        )
        result = queryset._cache_or_return_result(queryset._embed_parent_in_result(result))
        queryset._cache_count = 1
        queryset._cache_first = result
        queryset._cache_last = result
        return result

    async def first(self, **kwargs: Any) -> SaffierModel | None:
        """
        Returns the first record of a given queryset.
        """
        if not kwargs:
            if self._cache_count == 0:
                return None
            if self._cache_first is not None:
                return self._cache_first

        queryset: QuerySet = self._clone()
        if kwargs:
            queryset = queryset.filter(**kwargs)

        if not queryset._order_by:
            queryset = queryset.order_by(*queryset.pknames)

        queryset = queryset.limit(1)
        expression, tables_and_models = queryset._build_select_with_tables()
        queryset._set_query_expression(expression)
        if queryset._select_related:
            self._cached_select_related_expression = expression

        check_db_connection(queryset.database)
        async with queryset.database as database:
            rows = await database.fetch_all(expression)
        if not rows:
            return None

        result = await queryset._hydrate_row(
            queryset,
            rows[0],
            tables_and_models,
            is_only_fields=bool(queryset._only),
            is_defer_fields=bool(queryset._defer),
        )
        result = queryset._cache_or_return_result(queryset._embed_parent_in_result(result))
        if queryset.is_m2m:
            return getattr(result, queryset.m2m_related)
        if not kwargs:
            self._cache_first = result
        return result

    async def last(self, **kwargs: Any) -> SaffierModel | None:
        """
        Returns the last record of a given queryset.
        """
        if not kwargs:
            if self._cache_count == 0:
                return None
            if self._cache_last is not None:
                return self._cache_last

        queryset: QuerySet = self._clone()
        if kwargs:
            queryset = queryset.filter(**kwargs)

        if not queryset._order_by:
            queryset = queryset.order_by(*queryset.pknames)

        queryset = queryset.reverse().limit(1)
        expression, tables_and_models = queryset._build_select_with_tables()
        queryset._set_query_expression(expression)
        if queryset._select_related:
            self._cached_select_related_expression = expression

        check_db_connection(queryset.database)
        async with queryset.database as database:
            rows = await database.fetch_all(expression)
        if not rows:
            return None

        result = await queryset._hydrate_row(
            queryset,
            rows[0],
            tables_and_models,
            is_only_fields=bool(queryset._only),
            is_defer_fields=bool(queryset._defer),
        )
        result = queryset._cache_or_return_result(queryset._embed_parent_in_result(result))
        if queryset.is_m2m:
            return getattr(result, queryset.m2m_related)
        if not kwargs:
            self._cache_last = result
        return result

    def _filter_lookup_kwargs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key in self.model_class.fields and self.model_class.fields[key].has_column()
        }

    def _extract_model_reference_kwargs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key in self.model_class.fields
            and getattr(self.model_class.fields[key], "is_model_reference", False)
        }

    async def _persist_model_reference_kwargs(
        self,
        instance: SaffierModel,
        payload: dict[str, Any],
    ) -> None:
        if not payload:
            return
        for key, value in payload.items():
            setattr(instance, key, value)
        await instance._persist_model_references(set(payload))

    async def create(self, *model_refs: Any, **kwargs: Any) -> SaffierModel:
        """
        Creates a record in a specific table.
        """
        queryset: QuerySet = self._clone()
        check_db_connection(queryset.database)
        explicit_input = queryset.model_class.normalize_field_kwargs(dict(kwargs))
        explicit_input = queryset.model_class.merge_model_refs(model_refs, explicit_input)
        many_to_many_values: dict[str, list[Any]] = {}
        for field_name, field in queryset.model_class.fields.items():
            if not isinstance(field, saffier_fields.ManyToManyField):
                continue
            if field_name not in kwargs:
                continue
            many_to_many_values[field_name] = queryset._normalize_many_to_many_values(
                field,
                kwargs.pop(field_name),
            )

        kwargs = queryset._validate_kwargs(**kwargs)
        kwargs = queryset.model_class.merge_model_refs(model_refs, kwargs)
        instance_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in explicit_input
            or key not in queryset.model_class.fields
            or not queryset.model_class.fields[key].has_column()
        }
        instance = queryset.model_class(**instance_kwargs)
        instance.table = queryset.table
        instance = await instance.save(force_save=True, values=set(explicit_input.keys()))

        for field_name, related_values in many_to_many_values.items():
            relation = getattr(instance, field_name)
            for related_value in related_values:
                if getattr(related_value, "pk", None) is None:
                    raise QuerySetError(
                        detail=(
                            f"Cannot assign unsaved related object to '{field_name}' while creating "
                            f"'{queryset.model_class.__name__}'."
                        )
                    )
                await relation.add(related_value)

        self._clear_cache(keep_result_cache=True, keep_cached_selected=True)
        self._cache.update(self.model_class, [instance])
        return instance

    async def bulk_create(self, objs: list[dict]) -> None:
        """
        Bulk creates records in a table
        """
        queryset: QuerySet = self._clone()
        new_objs = []
        for obj in objs:
            validated_obj = queryset._validate_kwargs(**obj)
            db_values = queryset.model_class.extract_column_values(
                validated_obj,
                phase="prepare_insert",
                instance=queryset,
                evaluate_values=True,
            )
            new_objs.append(db_values)

        if not new_objs:
            return
        expression = queryset.table.insert()
        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            await database.execute_many(expression, new_objs)

    async def bulk_update(self, objs: list[SaffierModel], fields: list[str]) -> None:
        """
        Bulk updates records in a table.

        A similar solution was suggested here: https://github.com/encode/orm/pull/148

        It is thought to be a clean approach to a simple problem so it was added here and
        refactored to be compatible with Saffier.
        """
        queryset: QuerySet = self._clone()

        new_fields = {}
        for key, field in queryset.model_class.fields.items():
            if key in fields and field.has_column():
                field_validator = field.validator
                if field_validator.read_only:
                    field_validator = copy.copy(field_validator)
                    field_validator.read_only = False
                new_fields[key] = field_validator

        validator = Schema(fields=new_fields)

        new_objs = []
        for obj in objs:
            new_obj = {}
            for key, value in obj.__dict__.items():
                if key in fields and key in queryset.model_class.fields:
                    if not queryset.model_class.fields[key].has_column():
                        continue
                    new_obj[key] = value
            new_objs.append(new_obj)

        new_objs = [
            queryset.model_class.extract_column_values(
                queryset._update_auto_now_fields(
                    validator.check(obj), queryset.model_class.fields
                ),
                is_update=True,
                is_partial=True,
                phase="prepare_update",
                instance=queryset,
            )
            for obj in new_objs
        ]

        pk_bind_names = {pk_name: f"__pk_{pk_name}" for pk_name in queryset.pknames}
        expression = queryset.table.update().where(
            sqlalchemy.and_(
                *[
                    getattr(queryset.table.c, pk_name)
                    == sqlalchemy.bindparam(pk_bind_names[pk_name])
                    for pk_name in queryset.pknames
                ]
            )
        )
        kwargs: dict[str, Any] = {
            field: sqlalchemy.bindparam(field) for obj in new_objs for field in obj
        }
        pks = [
            {pk_bind_names[pk_name]: getattr(obj, pk_name) for pk_name in queryset.pknames}
            for obj in objs
        ]

        query_list = []
        for pk, value in zip(pks, new_objs):  # noqa
            query_list.append({**pk, **value})

        expression = expression.values(kwargs)
        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            await database.execute_many(expression, query_list)

    async def raw_delete(
        self,
        use_models: bool = False,
        remove_referenced_call: str | bool = False,
    ) -> int:
        queryset: QuerySet = self._clone()
        if getattr(queryset.model_class, "__require_model_based_deletion__", False):
            use_models = True

        if use_models:
            row_count = 0
            for model in await queryset.all():
                row_count += await model.raw_delete(
                    skip_post_delete_hooks=False,
                    remove_referenced_call=remove_referenced_call,
                )
            return row_count

        count_expression = sqlalchemy.func.count().select().select_from(queryset.table)
        if queryset.filter_clauses:
            count_expression = queryset._build_filter_clauses_expression(
                queryset.filter_clauses, expression=count_expression
            )

        if queryset.or_clauses:
            count_expression = queryset._build_or_clauses_expression(
                queryset.or_clauses, expression=count_expression
            )

        check_db_connection(queryset.database)
        async with queryset.database as database:
            row_count = cast("int", await database.fetch_val(count_expression) or 0)
        expression = queryset.table.delete()

        if queryset.filter_clauses:
            expression = queryset._build_filter_clauses_expression(
                queryset.filter_clauses, expression=expression
            )

        if queryset.or_clauses:
            expression = queryset._build_or_clauses_expression(queryset.or_clauses, expression)

        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            await database.execute(expression)
        return row_count

    async def delete(self, use_models: bool = False) -> int:
        queryset: QuerySet = self._clone()
        if getattr(queryset.model_class, "__require_model_based_deletion__", False):
            use_models = True
        await self.model_class.signals.pre_delete.send(
            sender=self.__class__,
            instance=self,
            model_instance=None,
        )

        row_count = await queryset.raw_delete(
            use_models=use_models,
            remove_referenced_call=False,
        )

        await self.model_class.signals.post_delete.send(
            sender=self.__class__,
            instance=self,
            model_instance=None,
            row_count=row_count,
        )
        return row_count

    async def update(self, **kwargs: Any) -> None:
        """
        Updates a record in a specific table with the given kwargs.
        """
        queryset: QuerySet = self._clone()
        normalized_kwargs = queryset.model_class.normalize_field_kwargs(kwargs)
        db_kwargs = {
            key: value
            for key, value in normalized_kwargs.items()
            if key in queryset.model_class.fields and queryset.model_class.fields[key].has_column()
        }
        fields = {
            key: (
                copy.copy(field.validator)
                if key in db_kwargs and field.validator.read_only
                else field.validator
            )
            for key, field in queryset.model_class.fields.items()
            if key in db_kwargs
        }
        for field_validator in fields.values():
            if field_validator.read_only:
                field_validator.read_only = False

        validator = Schema(fields=fields)
        db_kwargs = queryset.model_class.extract_column_values(
            validator.check(db_kwargs),
            is_update=True,
            is_partial=True,
            phase="prepare_update",
            instance=queryset,
        )
        db_kwargs = queryset._update_auto_now_fields(db_kwargs, queryset.model_class.fields)

        await self.model_class.signals.pre_update.send(
            sender=self.__class__, instance=self, kwargs=db_kwargs
        )

        if not db_kwargs:
            await self.model_class.signals.post_update.send(sender=self.__class__, instance=self)
            return

        expression = queryset.table.update().values(**db_kwargs)

        for filter_clause in queryset.filter_clauses:
            expression = expression.where(filter_clause)

        queryset._set_query_expression(expression)
        check_db_connection(queryset.database)
        async with queryset.database as database:
            await database.execute(expression)

        await self.model_class.signals.post_update.send(sender=self.__class__, instance=self)

    async def get_or_create(
        self,
        *model_refs: Any,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[SaffierModel, bool]:
        """
        Creates a record in a specific table or updates if already exists.
        """
        queryset: QuerySet = self._clone()
        defaults = defaults or {}
        lookup_kwargs = queryset._filter_lookup_kwargs(kwargs)
        ref_payload = dict(kwargs)
        ref_payload.update(defaults)
        ref_kwargs = queryset._extract_model_reference_kwargs(
            queryset.model_class.merge_model_refs(model_refs, ref_payload)
        )
        try:
            instance = await queryset.get(**lookup_kwargs)
            await queryset._persist_model_reference_kwargs(instance, ref_kwargs)
            return instance, False
        except ObjectNotFound:
            kwargs.update(defaults)
            instance = await queryset.create(*model_refs, **kwargs)
            return instance, True

    async def bulk_get_or_create(
        self,
        objs: list[dict[str, Any] | SaffierModel],
        unique_fields: list[str] | None = None,
    ) -> list[SaffierModel]:
        """
        Bulk gets or creates records.

        When `unique_fields` is provided, existing records are fetched by those fields.
        Missing records are created. Duplicate lookup payloads inside `objs` are collapsed.
        """
        queryset: QuerySet = self._clone()
        instances: list[SaffierModel] = []
        seen_lookups: set[tuple[tuple[str, Any], ...]] = set()

        for obj in objs:
            values = obj if isinstance(obj, dict) else obj.extract_db_fields()

            if unique_fields:
                lookup = {}
                for field in unique_fields:
                    if field not in values:
                        raise QuerySetError(
                            detail=f"Field '{field}' is required in unique_fields lookups."
                        )
                    lookup[field] = values[field]

                lookup_key = tuple(sorted(lookup.items()))
                if lookup_key in seen_lookups:
                    continue
                seen_lookups.add(lookup_key)

                instance = await queryset.get_or_none(**lookup)
                if instance is not None:
                    instances.append(instance)
                    continue

            instance = await queryset.create(**values)
            instances.append(instance)

        return instances

    bulk_select_or_insert = bulk_get_or_create

    async def update_or_create(
        self,
        *model_refs: Any,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[SaffierModel, bool]:
        """
        Updates a record in a specific table or creates a new one.
        """
        queryset: QuerySet = self._clone()
        defaults = defaults or {}
        lookup_kwargs = queryset._filter_lookup_kwargs(kwargs)
        ref_payload = dict(kwargs)
        ref_payload.update(defaults)
        ref_kwargs = queryset._extract_model_reference_kwargs(
            queryset.model_class.merge_model_refs(model_refs, ref_payload)
        )
        try:
            instance = await queryset.get(**lookup_kwargs)
            await instance.update(**defaults)
            await queryset._persist_model_reference_kwargs(instance, ref_kwargs)
            return instance, False
        except ObjectNotFound:
            kwargs.update(defaults)
            instance = await queryset.create(*model_refs, **kwargs)
            return instance, True

    async def contains(self, instance: SaffierModel) -> bool:
        """Returns true if the QuerySet contains the provided object.
        False if otherwise.
        """
        queryset: QuerySet = self._clone()
        if getattr(instance, "pk", None) is None:
            raise ValueError("'obj' must be a model or reflect model instance.")
        return await queryset.filter(pk=instance.pk).exists()

    def _combine(
        self,
        other: "QuerySet",
        op: str,
        *,
        all_: bool = False,
    ) -> "CombinedQuerySet":
        if not isinstance(other, QuerySet):
            raise TypeError("other must be a QuerySet")

        if self.model_class is not other.model_class:
            raise QuerySetError(detail="Both querysets must have the same model_class to combine.")

        if self.database is not other.database and str(self.database.url) != str(
            other.database.url
        ):
            raise QuerySetError(detail="Both querysets must use the same database.")

        op_name = f"{op}_all" if all_ else op
        return CombinedQuerySet(left=self, right=other, op=op_name)

    def union(self, other: "QuerySet", *, all: bool = False) -> "CombinedQuerySet":
        """
        Returns the SQL UNION of this queryset and another queryset.
        """
        return self._combine(other, "union", all_=all)

    def union_all(self, other: "QuerySet") -> "CombinedQuerySet":
        """
        Shortcut for UNION ALL.
        """
        return self._combine(other, "union", all_=True)

    def intersect(self, other: "QuerySet", *, all: bool = False) -> "CombinedQuerySet":
        """
        Returns the SQL INTERSECT of this queryset and another queryset.
        """
        return self._combine(other, "intersect", all_=all)

    def intersect_all(self, other: "QuerySet") -> "CombinedQuerySet":
        """
        Shortcut for INTERSECT ALL.
        """
        return self._combine(other, "intersect", all_=True)

    def except_(self, other: "QuerySet", *, all: bool = False) -> "CombinedQuerySet":
        """
        Returns the SQL EXCEPT of this queryset and another queryset.
        """
        return self._combine(other, "except", all_=all)

    def except_all(self, other: "QuerySet") -> "CombinedQuerySet":
        """
        Shortcut for EXCEPT ALL.
        """
        return self._combine(other, "except", all_=True)

    def select_for_update(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
        read: bool = False,
        key_share: bool = False,
        of: Sequence[type["Model"]] | None = None,
    ) -> "QuerySet":
        """
        Request row-level locks via SELECT ... FOR UPDATE semantics.
        """
        queryset: QuerySet = self._clone()
        payload: dict[str, Any] = {
            "nowait": bool(nowait),
            "skip_locked": bool(skip_locked),
            "read": bool(read),
            "key_share": bool(key_share),
        }
        if of:
            payload["of"] = tuple(of)
        queryset._for_update = payload
        return queryset

    def transaction(self, *, force_rollback: bool = False, **kwargs: Any) -> Any:
        """
        Returns a database transaction context manager bound to this QuerySet database.
        """
        return self.database.transaction(force_rollback=force_rollback, **kwargs)

    def _embed_parent_in_result(self, result: SaffierModel) -> SaffierModel:
        """
        Returns the embedded parent target when the queryset was created from a relation.
        """
        if not self.embed_parent:
            return result

        new_result: Any = result
        for part in self.embed_parent[0].split("__"):
            new_result = getattr(new_result, part)

        if self.embed_parent[1]:
            try:
                setattr(new_result, self.embed_parent[1], result)
            except AttributeError:
                object.__setattr__(new_result, self.embed_parent[1], result)
        return cast("SaffierModel", new_result)

    async def as_select_with_tables(self) -> tuple[Any, dict[str, tuple[Any, Any]]]:
        """
        Returns the SQLAlchemy select expression together with the table mapping.
        """
        return self._build_select_with_tables()

    async def as_select(self) -> Any:
        """
        Returns the SQLAlchemy select expression for the queryset.
        """
        return (await self.as_select_with_tables())[0]

    async def _execute(self) -> Any:
        records = await self._all(**self.extra)
        return records

    async def _execute_iterate(
        self,
        fetch_all_at_once: bool = False,
    ) -> AsyncIterator[SaffierModel]:
        queryset: QuerySet = self._clone()

        if queryset.is_m2m:
            queryset.distinct_on = [queryset.m2m_related]

        if queryset.extra:
            queryset = queryset.filter(**queryset.extra)

        expression, tables_and_models = queryset._build_select_with_tables()
        queryset._set_query_expression(expression)

        is_only_fields = bool(queryset._only)
        is_defer_fields = bool(queryset._defer)
        queryset.model_class.raw_query = queryset.sql

        if not fetch_all_at_once and bool(getattr(queryset.database, "force_rollback", False)):
            warnings.warn(
                'Using queryset iterations with "Database"-level force_rollback set is risky. '
                "Deadlocks can occur because only one connection is used.",
                UserWarning,
                stacklevel=3,
            )
        if queryset._prefetch_related:
            fetch_all_at_once = True

        check_db_connection(queryset.database)
        if fetch_all_at_once:
            async with queryset.database as database:
                rows = await database.fetch_all(expression)

            for row in rows:
                result = await queryset._hydrate_row(
                    queryset,
                    row,
                    tables_and_models,
                    is_only_fields=is_only_fields,
                    is_defer_fields=is_defer_fields,
                )

                if not queryset.is_m2m:
                    yield queryset._embed_parent_in_result(result)
                else:
                    yield getattr(result, queryset.m2m_related)
            return

        async with queryset.database as database:
            async for row in database.iterate(expression, chunk_size=queryset._batch_size):
                result = await queryset._hydrate_row(
                    queryset,
                    row,
                    tables_and_models,
                    is_only_fields=is_only_fields,
                    is_defer_fields=is_defer_fields,
                )

                if not queryset.is_m2m:
                    yield queryset._embed_parent_in_result(result)
                else:
                    yield getattr(result, queryset.m2m_related)

    def __await__(
        self,
    ) -> Generator[Any, None, list[SaffierModel]]:
        return self._execute().__await__()

    def __class_getitem__(cls, *args: Any, **kwargs: Any) -> Any:
        return cls


class CombinedQuerySet(QuerySet):
    """
    QuerySet representing a SQL set operation between two querysets.
    """

    def __init__(
        self,
        left: QuerySet,
        right: QuerySet,
        *,
        op: str = "union",
    ) -> None:
        super().__init__(
            model_class=left.model_class,
            database=left.database,
            using_schema=left.using_schema,
            table=left.table,
        )
        self._left = left
        self._right = right
        self._op = op

    def _clone(self) -> "CombinedQuerySet":
        queryset = cast("CombinedQuerySet", super()._clone())
        queryset._left = self._left
        queryset._right = self._right
        queryset._op = self._op
        return queryset

    def _build_select_with_tables(self) -> tuple[Any, dict[str, tuple[Any, Any]]]:
        queryset = self._clone()

        if queryset.filter_clauses or queryset.or_clauses:
            raise QuerySetError(
                detail="Filter/exclude/or_ are not supported after combining querysets. "
                "Apply filters before union/intersect/except."
            )

        if queryset._select_related or queryset._prefetch_related:
            raise QuerySetError(
                detail="select_related/prefetch_related are not supported on combined querysets."
            )

        if queryset._for_update:
            raise QuerySetError(
                detail="select_for_update() is not supported on combined querysets."
            )

        left_expression = queryset._left._clone()._build_select()
        right_expression = queryset._right._clone()._build_select()

        if len(left_expression.selected_columns) != len(right_expression.selected_columns):
            raise QuerySetError(
                detail="Combined querysets must select the same number of columns."
            )

        if queryset._op == "union":
            combined_expression = left_expression.union(right_expression)
        elif queryset._op == "union_all":
            combined_expression = left_expression.union_all(right_expression)
        elif queryset._op == "intersect":
            combined_expression = left_expression.intersect(right_expression)
        elif queryset._op == "intersect_all":
            combined_expression = left_expression.intersect_all(right_expression)
        elif queryset._op == "except":
            combined_expression = left_expression.except_(right_expression)
        elif queryset._op == "except_all":
            combined_expression = left_expression.except_all(right_expression)
        else:
            raise QuerySetError(detail=f"Unsupported set operation: {queryset._op}")

        subquery = combined_expression.subquery("saffier_combined")
        expression = sqlalchemy.select(subquery)
        tables_and_models = {"": (subquery, queryset.model_class)}

        if queryset._order_by:
            ordering = []
            for value in queryset._order_by:
                reverse = value.startswith("-")
                field_name = value.lstrip("-")
                try:
                    column = subquery.c[field_name]
                except KeyError as exc:
                    raise QuerySetError(
                        detail=f"Cannot order combined queryset by unknown field '{field_name}'."
                    ) from exc
                ordering.append(column.desc() if reverse else column.asc())
            expression = expression.order_by(*ordering)

        if queryset._group_by:
            groups = []
            for value in queryset._group_by:
                field_name = value.lstrip("-")
                try:
                    groups.append(subquery.c[field_name])
                except KeyError as exc:
                    raise QuerySetError(
                        detail=f"Cannot group combined queryset by unknown field '{field_name}'."
                    ) from exc
            expression = expression.group_by(*groups)

        if queryset.distinct_on is not None:
            if queryset.distinct_on:
                try:
                    distinct_fields = [subquery.c[field] for field in queryset.distinct_on]
                except KeyError as exc:
                    raise QuerySetError(
                        detail=f"Unknown field in distinct() for combined queryset: {exc.args[0]}"
                    ) from exc
                expression = expression.distinct(*distinct_fields)
            else:
                expression = expression.distinct()

        if queryset.limit_count:
            expression = expression.limit(queryset.limit_count)

        if queryset._offset:
            expression = expression.offset(queryset._offset)

        queryset._expression = expression  # type: ignore
        return expression, tables_and_models

    def _build_select(self) -> Any:
        return self._build_select_with_tables()[0]
