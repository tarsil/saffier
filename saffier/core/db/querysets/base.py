import copy
from collections.abc import AsyncIterator, Generator, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    cast,
)

import sqlalchemy

import saffier
from saffier.conf import settings
from saffier.core.db import fields as saffier_fields
from saffier.core.db.context_vars import get_schema
from saffier.core.db.fields import CharField, TextField
from saffier.core.db.querysets.mixins import QuerySetPropsMixin, SaffierModel, TenancyMixin
from saffier.core.db.querysets.prefetch import PrefetchMixin
from saffier.core.db.querysets.protocols import AwaitableQuery
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
    ) -> None:
        super().__init__(model_class=model_class)
        self.model_class = cast("type[Model]", model_class)
        self.filter_clauses = [] if filter_clauses is None else filter_clauses
        self.or_clauses = [] if or_clauses is None else or_clauses
        self.limit_count = limit_count
        self._select_related = [] if select_related is None else select_related
        self._prefetch_related = [] if prefetch_related is None else prefetch_related
        self._offset = limit_offset
        self._order_by = [] if order_by is None else order_by
        self._group_by = [] if group_by is None else group_by
        self.distinct_on = [] if distinct_on is None else distinct_on
        self._only = [] if only_fields is None else only_fields
        self._defer = [] if defer_fields is None else defer_fields
        self._expression = None
        self._cache = None
        self._m2m_related = m2m_related  # type: ignore
        self.using_schema = using_schema
        self._exclude_secrets = exclude_secrets or False
        self.extra: dict[str, Any] = {}
        self._for_update = for_update

        if self.is_m2m and not self._m2m_related:
            self._m2m_related = self.model_class.meta.multi_related[0]

        if table is not None:
            self.table = table
        if database is not None:
            self.database = database

    def _build_order_by_expression(self, order_by: Any, expression: Any) -> Any:
        """Builds the order by expression"""
        order_by = list(map(self._prepare_order_by, order_by))
        expression = expression.order_by(*order_by)
        return expression

    def _build_group_by_expression(self, group_by: Any, expression: Any) -> Any:
        """Builds the group by expression"""
        group_by = list(map(self._prepare_group_by, group_by))
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
        if len(or_clauses) == 1:
            clause = or_clauses[0]
        else:
            clause = sqlalchemy.sql.or_(*or_clauses)
        expression = expression.where(clause)
        return expression

    def _build_select_distinct(self, distinct_on: Any, expression: Any) -> Any:
        """Filters selects only specific fields"""
        distinct_on = list(map(self._prepare_fields_for_distinct, distinct_on))
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

    def _build_tables_select_from_relationship(self) -> Any:
        """
        Builds the tables relationships and joins.
        When a table contains more than one foreign key pointing to the same
        destination table, a lookup for the related field is made to understand
        from which foreign key the table is looked up from.
        """
        queryset: QuerySet = self._clone()

        tables = [queryset.table]
        select_from = queryset.table

        # Select related
        for item in queryset._select_related:
            # For m2m relationships
            model_class = queryset.model_class
            has_many_fk_same_table = False

            for part in item.split("__"):
                try:
                    model_class = model_class.fields[part].target
                except KeyError:
                    # Check related fields
                    model_class = getattr(model_class, part).related_from
                    has_many_fk_same_table, keys = self._is_multiple_foreign_key(model_class)

                if queryset.using_schema is not None:
                    table = model_class.table_schema(queryset.using_schema)
                else:
                    table = model_class.table

                # If there is multiple FKs to the same table
                if not has_many_fk_same_table:
                    select_from = sqlalchemy.sql.join(select_from, table)  # type: ignore
                else:
                    lookup_field = None

                    # Extract the table field from the related
                    # Assign to a lookup_field
                    for values in keys:
                        field, _, related_name = values
                        if related_name == part:
                            lookup_field = field
                            break

                    select_from = sqlalchemy.sql.join(  # type: ignore
                        select_from,
                        table,
                        select_from.c.id == getattr(table.c, lookup_field),
                    )

                tables.append(table)
        return tables, select_from

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

    def _build_select(self) -> Any:
        """
        Builds the query select based on the given parameters and filters.
        """
        queryset: QuerySet = self._clone()

        queryset._validate_only_and_defer()
        tables, select_from = queryset._build_tables_select_from_relationship()
        expression = sqlalchemy.sql.select(*tables)
        expression = expression.select_from(select_from)

        if queryset._only:
            expression = expression.with_only_columns(*queryset._only)

        if queryset._defer:
            columns = [
                column for column in select_from.columns if column.name not in queryset._defer
            ]
            expression = expression.with_only_columns(*columns)

        if queryset._exclude_secrets:
            model_columns = queryset._secret_recursive_names(model_class=queryset.model_class)
            columns = [column for column in select_from.columns if column.name in model_columns]
            expression = expression.with_only_columns(*columns)

        if queryset.filter_clauses:
            expression = queryset._build_filter_clauses_expression(
                queryset.filter_clauses, expression=expression
            )

        if queryset.or_clauses:
            expression = queryset._build_or_clauses_expression(
                queryset.or_clauses, expression=expression
            )

        if queryset._order_by:
            expression = queryset._build_order_by_expression(
                queryset._order_by, expression=expression
            )

        if queryset.limit_count:
            expression = expression.limit(queryset.limit_count)

        if queryset._offset:
            expression = expression.offset(queryset._offset)

        if queryset._group_by:
            expression = queryset._build_group_by_expression(
                queryset._group_by, expression=expression
            )

        if queryset.distinct_on:
            expression = queryset._build_select_distinct(
                queryset.distinct_on, expression=expression
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
        return expression

    def _filter_query(self, exclude: bool = False, or_: bool = False, **kwargs: Any) -> "QuerySet":
        from saffier.core.db.models.model import Model

        clauses = []
        filter_clauses = self.filter_clauses
        or_clauses = self.or_clauses
        select_related = list(self._select_related)
        prefetch_related = list(self._prefetch_related)

        if kwargs.get("pk"):
            pk_name = self.model_class.pkname
            kwargs[pk_name] = kwargs.pop("pk")

        # Making sure for queries we use the main class and not the proxy
        # And enable the parent
        if self.model_class.is_proxy_model:
            self.model_class = self.model_class.parent

        for key, value in kwargs.items():
            if "__" in key:
                parts = key.split("__")

                # Determine if we should treat the final part as a
                # filter operator or as a related field.
                if parts[-1] in settings.filter_operators:
                    op = parts[-1]
                    field_name = parts[-2]
                    related_parts = parts[:-2]
                else:
                    op = "exact"
                    field_name = parts[-1]
                    related_parts = parts[:-1]

                model_class = self.model_class
                if related_parts:
                    # Add any implied select_related
                    related_str = "__".join(related_parts)
                    if related_str not in select_related:
                        select_related.append(related_str)

                    # Walk the relationships to the actual model class
                    # against which the comparison is being made.
                    for part in related_parts:
                        try:
                            model_class = model_class.fields[part].target
                        except KeyError:
                            model_class = getattr(model_class, part).related_from

                column = model_class.table.columns[field_name]

            else:
                op = "exact"
                try:
                    column = self.table.columns[key]
                except KeyError as error:
                    # Check for related fields
                    # if an Attribute error is raised, we need to make sure
                    # It raises the KeyError from the previous check
                    try:
                        model_class = getattr(self.model_class, key).related_to
                        column = model_class.table.columns[settings.default_related_lookup_field]
                    except AttributeError:
                        raise KeyError(str(error)) from error

            # Map the operation code onto SQLAlchemy's ColumnElement
            # https://docs.sqlalchemy.org/en/latest/core/sqlelement.html#sqlalchemy.sql.expression.ColumnElement
            op_attr = settings.filter_operators[op]
            has_escaped_character = False

            if op in ["contains", "icontains"]:
                has_escaped_character = any(c for c in self.ESCAPE_CHARACTERS if c in value)
                if has_escaped_character:
                    # enable escape modifier
                    for char in self.ESCAPE_CHARACTERS:
                        value = value.replace(char, f"\\{char}")
                value = f"%{value}%"

            if isinstance(value, Model):
                value = value.pk

            clause = getattr(column, op_attr)(value)
            clause.modifiers["escape"] = "\\" if has_escaped_character else None

            clauses.append(clause)

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
            ),
        )

    def _validate_kwargs(self, **kwargs: Any) -> Any:
        fields = self.model_class.fields
        validator = Schema(fields={key: value.validator for key, value in fields.items()})
        kwargs = validator.check(kwargs)
        for key, value in fields.items():
            if value.validator.read_only and value.validator.has_default():
                kwargs[key] = value.validator.get_default_value()
        return kwargs

    def _prepare_order_by(self, order_by: str) -> Any:
        reverse = order_by.startswith("-")
        order_by = order_by.lstrip("-")
        order_col = self.table.columns[order_by]
        return order_col.desc() if reverse else order_col

    def _prepare_group_by(self, group_by: str) -> Any:
        group_by = group_by.lstrip("-")
        group_col = self.table.columns[group_by]
        return group_col

    def _prepare_fields_for_distinct(self, distinct_on: str) -> Any:
        _distinct_on: sqlalchemy.Column = self.table.columns[distinct_on]
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
        if not self.model_class.meta.registry.db_schema:
            schema = get_schema()
            if self.using_schema is None and schema is not None:
                self.using_schema = schema
            queryset.model_class.table = self.model_class.build(self.using_schema)

        queryset.filter_clauses = copy.copy(self.filter_clauses)
        queryset.or_clauses = copy.copy(self.or_clauses)
        queryset.limit_count = self.limit_count
        queryset._select_related = copy.copy(self._select_related)
        queryset._prefetch_related = copy.copy(self._prefetch_related)
        queryset._offset = self._offset
        queryset._order_by = copy.copy(self._order_by)
        queryset._group_by = copy.copy(self._group_by)
        queryset.distinct_on = copy.copy(self.distinct_on)
        queryset._expression = self._expression
        queryset._cache = self._cache
        queryset._m2m_related = self._m2m_related
        queryset._only = copy.copy(self._only)
        queryset._defer = copy.copy(self._defer)
        queryset._database = self.database
        queryset.table = self.table
        queryset.extra = self.extra
        queryset._exclude_secrets = self._exclude_secrets
        queryset.using_schema = self.using_schema
        queryset._for_update = copy.copy(self._for_update)

        return queryset


class QuerySet(BaseQuerySet, QuerySetProtocol):
    """
    QuerySet object used for query retrieving.
    """

    def __get__(self, instance: Any, owner: Any) -> "QuerySet":
        return self.__class__(model_class=owner)

    @property
    def sql(self) -> str:
        return str(self._expression)

    @sql.setter
    def sql(self, value: Any) -> None:
        self._expression = value

    async def __aiter__(self) -> AsyncIterator[SaffierModel]:
        for value in await self:
            yield value

    def _set_query_expression(self, expression: Any) -> None:
        """
        Sets the value of the sql property to the expression used.
        """
        self.sql = expression
        self.model_class.raw_query = self.sql

    def _filter_or_exclude(
        self,
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
        exclude: bool = False,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters or excludes a given clause for a specific QuerySet.
        """
        queryset: QuerySet = self._clone()

        if clause is None:
            if not exclude:
                return queryset._filter_query(**kwargs)
            return queryset._filter_query(exclude=exclude, **kwargs)

        queryset.filter_clauses.append(clause)
        return queryset

    def filter(
        self,
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the given kwargs and clause.
        """
        return self._filter_or_exclude(clause=clause, **kwargs)

    def or_(
        self,
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Filters the QuerySet by the OR operand.
        """
        queryset: QuerySet = self._clone()
        queryset = self.filter(clause=clause, or_=True, **kwargs)
        return queryset

    def and_(
        self,
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
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
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
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
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Exactly the same as the filter but for the exclude.
        """
        queryset: QuerySet = self._clone()
        queryset = self._filter_or_exclude(clause=clause, exclude=True, **kwargs)
        return queryset

    def exclude_secrets(
        self,
        clause: sqlalchemy.sql.expression.BinaryExpression | None = None,
        **kwargs: Any,
    ) -> "QuerySet":
        """
        Excludes any field that contains the `secret=True` declared from being leaked.
        """
        queryset: QuerySet = self._clone()
        queryset._exclude_secrets = True
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
            queryset = queryset.order_by(queryset.model_class.pkname)

        queryset._order_by = tuple(
            value[1:] if value.startswith("-") else f"-{value}" for value in queryset._order_by
        )
        return queryset

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

    def distinct(self, *distinct_on: str) -> "QuerySet":
        """
        Returns a queryset with distinct results.
        """
        queryset: QuerySet = self._clone()
        queryset.distinct_on = distinct_on
        return queryset

    def only(self, *fields: Sequence[str]) -> "QuerySet":
        """
        Returns a list of models with the selected only fields and always the primary
        key.
        """
        only_fields = [sqlalchemy.text(field) for field in fields]
        if self.model_class.pkname not in fields:
            only_fields.insert(0, sqlalchemy.text(self.model_class.pkname))

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

        related = list(queryset._select_related) + related
        queryset._select_related = related
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
        queryset: QuerySet = self._clone()
        expression = queryset._build_select()
        expression = sqlalchemy.exists(expression).select()
        queryset._set_query_expression(expression)
        _exists = await queryset.database.fetch_val(expression)
        return cast("bool", _exists)

    async def count(self, **kwargs: Any) -> int:
        """
        Returns an indicating the total records.
        """
        queryset: QuerySet = self._clone()
        expression = queryset._build_select().alias("subquery_for_count")
        expression = sqlalchemy.func.count().select().select_from(expression)
        queryset._set_query_expression(expression)
        _count = await queryset.database.fetch_val(expression)
        return cast("int", _count)

    async def get_or_none(self, **kwargs: Any) -> SaffierModel | None:
        """
        Fetch one object matching the parameters or returns None.
        """
        queryset: QuerySet = self.filter(**kwargs)
        expression = queryset._build_select().limit(2)
        queryset._set_query_expression(expression)
        rows = await queryset.database.fetch_all(expression)

        if not rows:
            return None
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        return queryset.model_class.from_query_result(
            rows[0],
            select_related=queryset._select_related,
            using_schema=queryset.using_schema,
            exclude_secrets=queryset._exclude_secrets,
        )

    async def _all(self, **kwargs: Any) -> list[SaffierModel]:
        """
        Returns the queryset records based on specific filters
        """
        queryset: QuerySet = self._clone()

        if queryset.is_m2m:
            queryset.distinct_on = [queryset.m2m_related]

        if kwargs:
            return await queryset.filter(**kwargs).all()

        expression = queryset._build_select()
        queryset._set_query_expression(expression)

        rows = await queryset.database.fetch_all(expression)

        is_only_fields = True if queryset._only else False
        is_defer_fields = True if queryset._defer else False

        # Attach the raw query to the object
        queryset.model_class.raw_query = queryset.sql

        results = [
            queryset.model_class.from_query_result(
                row,
                select_related=queryset._select_related,
                prefetch_related=queryset._prefetch_related,
                is_only_fields=is_only_fields,
                only_fields=queryset._only,
                is_defer_fields=is_defer_fields,
                using_schema=queryset.using_schema,
                exclude_secrets=queryset._exclude_secrets,
            )
            for row in rows
        ]

        if not queryset.is_m2m:
            return results

        return [getattr(result, queryset.m2m_related) for result in results]

    def all(self, **kwargs: Any) -> "QuerySet":
        """
        Returns the queryset records based on specific filters
        """
        queryset: QuerySet = self._clone()
        queryset.extra = kwargs
        return queryset

    async def get(self, **kwargs: Any) -> SaffierModel:
        """
        Returns a single record based on the given kwargs.
        """
        queryset: QuerySet = self._clone()

        if kwargs:
            return await queryset.filter(**kwargs).get()

        expression = queryset._build_select().limit(2)
        rows = await queryset.database.fetch_all(expression)
        queryset._set_query_expression(expression)

        is_only_fields = True if queryset._only else False
        is_defer_fields = True if queryset._defer else False

        if not rows:
            raise ObjectNotFound()
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        return queryset.model_class.from_query_result(
            rows[0],
            select_related=queryset._select_related,
            is_only_fields=is_only_fields,
            only_fields=queryset._only,
            is_defer_fields=is_defer_fields,
            prefetch_related=queryset._prefetch_related,
            using_schema=queryset.using_schema,
            exclude_secrets=queryset._exclude_secrets,
        )

    async def first(self, **kwargs: Any) -> SaffierModel | None:
        """
        Returns the first record of a given queryset.
        """
        queryset: QuerySet = self._clone()
        if kwargs:
            return await queryset.filter(**kwargs).order_by("id").get()

        rows = await queryset.limit(1).order_by("id").all()
        if rows:
            return rows[0]
        return None

    async def last(self, **kwargs: Any) -> SaffierModel | None:
        """
        Returns the last record of a given queryset.
        """
        queryset: QuerySet = self._clone()
        if kwargs:
            return await queryset.filter(**kwargs).order_by("-id").get()

        rows = await queryset.order_by("-id").all()
        if rows:
            return rows[0]
        return None

    async def create(self, **kwargs: Any) -> SaffierModel:
        """
        Creates a record in a specific table.
        """
        queryset: QuerySet = self._clone()
        kwargs = queryset._validate_kwargs(**kwargs)
        instance = queryset.model_class(**kwargs)
        instance.table = queryset.table
        instance = await instance.save(force_save=True, values=kwargs)
        return instance

    async def bulk_create(self, objs: list[dict]) -> None:
        """
        Bulk creates records in a table
        """
        queryset: QuerySet = self._clone()
        new_objs = [queryset._validate_kwargs(**obj) for obj in objs]

        expression = queryset.table.insert().values(new_objs)
        queryset._set_query_expression(expression)
        await queryset.database.execute_many(expression)

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
            if key in fields:
                new_fields[key] = field.validator

        validator = Schema(fields=new_fields)

        new_objs = []
        for obj in objs:
            new_obj = {}
            for key, value in obj.__dict__.items():
                if key in fields:
                    new_obj[key] = value
            new_objs.append(new_obj)

        new_objs = [
            queryset._update_auto_now_fields(validator.check(obj), queryset.model_class.fields)
            for obj in new_objs
        ]

        pk = getattr(queryset.table.c, queryset.pkname)
        expression = queryset.table.update().where(
            pk == sqlalchemy.bindparam("__id" if queryset.pkname == "id" else queryset.pkname)
        )
        kwargs: dict[str, Any] = {
            field: sqlalchemy.bindparam(field) for obj in new_objs for field in obj
        }
        pks = [
            {"__id" if queryset.pkname == "id" else queryset.pkname: getattr(obj, queryset.pkname)}
            for obj in objs
        ]

        query_list = []
        for pk, value in zip(pks, new_objs):  # noqa
            query_list.append({**pk, **value})

        expression = expression.values(kwargs)
        queryset._set_query_expression(expression)
        await queryset.database.execute_many(expression, query_list)

    async def delete(self) -> None:
        queryset: QuerySet = self._clone()
        await self.model_class.signals.pre_delete.send(sender=self.__class__, instance=self)

        expression = queryset.table.delete()
        for filter_clause in queryset.filter_clauses:
            expression = expression.where(filter_clause)

        queryset._set_query_expression(expression)
        await queryset.database.execute(expression)

        await self.model_class.signals.post_delete.send(sender=self.__class__, instance=self)

    async def update(self, **kwargs: Any) -> None:
        """
        Updates a record in a specific table with the given kwargs.
        """
        queryset: QuerySet = self._clone()
        fields = {
            key: field.validator
            for key, field in queryset.model_class.fields.items()
            if key in kwargs
        }

        validator = Schema(fields=fields)
        kwargs = queryset._update_auto_now_fields(
            validator.check(kwargs), queryset.model_class.fields
        )

        await self.model_class.signals.pre_update.send(
            sender=self.__class__, instance=self, kwargs=kwargs
        )

        expression = queryset.table.update().values(**kwargs)

        for filter_clause in queryset.filter_clauses:
            expression = expression.where(filter_clause)

        queryset._set_query_expression(expression)
        await queryset.database.execute(expression)

        await self.model_class.signals.post_update.send(sender=self.__class__, instance=self)

    async def get_or_create(
        self, defaults: dict[str, Any], **kwargs: Any
    ) -> tuple[SaffierModel, bool]:
        """
        Creates a record in a specific table or updates if already exists.
        """
        queryset: QuerySet = self._clone()
        try:
            instance = await queryset.get(**kwargs)
            return instance, False
        except ObjectNotFound:
            kwargs.update(defaults)
            instance = await queryset.create(**kwargs)
            return instance, True

    async def update_or_create(
        self, defaults: dict[str, Any], **kwargs: Any
    ) -> tuple[SaffierModel, bool]:
        """
        Updates a record in a specific table or creates a new one.
        """
        queryset: QuerySet = self._clone()
        try:
            instance = await queryset.get(**kwargs)
            await instance.update(**defaults)
            return instance, False
        except ObjectNotFound:
            kwargs.update(defaults)
            instance = await queryset.create(**kwargs)
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

    async def _execute(self) -> Any:
        queryset: QuerySet = self._clone()
        records = await queryset._all(**queryset.extra)
        return records

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

    def _build_select(self) -> Any:
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

        if queryset.distinct_on:
            try:
                distinct_fields = [subquery.c[field] for field in queryset.distinct_on]
            except KeyError as exc:
                raise QuerySetError(
                    detail=f"Unknown field in distinct() for combined queryset: {exc.args[0]}"
                ) from exc
            expression = expression.distinct(*distinct_fields)

        if queryset.limit_count:
            expression = expression.limit(queryset.limit_count)

        if queryset._offset:
            expression = expression.offset(queryset._offset)

        queryset._expression = expression  # type: ignore
        return expression
