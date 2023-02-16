import copy
import typing

import sqlalchemy

from saffier.core.schemas import Schema
from saffier.core.utils import ModelUtil
from saffier.db.constants import FILTER_OPERATORS
from saffier.db.query.protocols import AwaitableQuery
from saffier.exceptions import DoesNotFound, MultipleObjectsReturned
from saffier.fields import CharField, TextField
from saffier.types import DictAny

if typing.TYPE_CHECKING:  # pragma: no cover
    from saffier.db.connection import Database
    from saffier.models import Model


SaffierModel = typing.TypeVar("SaffierModel", bound="Model")


class QuerySetProps:
    """
    Properties used by the Queryset are placed in isolation
    for clean access and maintainance.
    """

    @property
    def database(self) -> "Database":
        return self.model_class._meta.registry.database

    @property
    def table(self) -> sqlalchemy.Table:
        return self.model_class.table

    @property
    def schema(self):
        fields = {key: field.validator for key, field in self.model_class.fields.items()}
        return Schema(fields=fields)

    @property
    def pkname(self):
        return self.model_class.pkname


class BaseQuerySet(QuerySetProps, ModelUtil):
    def _build_order_by_expression(self, order_by, expression):
        """Builds the order by expression"""
        order_by = list(map(self._prepare_order_by, order_by))
        expression = expression.order_by(*order_by)
        return expression

    def _build_group_by_expression(self, group_by, expression):
        """Builds the group by expression"""
        group_by = list(map(self._prepare_group_by, group_by))
        expression = expression.group_by(*group_by)
        return expression

    def _build_filter_clauses_expression(self, filter_clauses, expression):
        """Builds the filter clauses expression"""
        if len(filter_clauses) == 1:
            clause = filter_clauses[0]
        else:
            clause = sqlalchemy.sql.and_(*filter_clauses)
        expression = expression.where(clause)
        return expression

    def _build_select_distinct(self, distinct_on, expression):
        """Filters selects only specific fields"""
        distinct_on = list(map(self._prepare_fields_for_distinct, distinct_on))
        expression = expression.distinct(*distinct_on)
        return expression

    def _build_tables_select_from_relationship(self):
        """
        Builds the tables relationships
        """
        tables = [self.table]
        select_from = self.table

        for item in self._select_related:
            model_class = self.model_class
            select_from = self.table

            for part in item.split("__"):
                model_class = model_class.fields[part].target
                table = model_class.table
                select_from = sqlalchemy.sql.join(select_from, table)
                tables.append(table)

        return tables, select_from

    def _build_select(self):
        """
        Builds the query select based on the given parameters and filters.
        """
        tables, select_from = self._build_tables_select_from_relationship()
        expression = sqlalchemy.sql.select(tables)
        expression = expression.select_from(select_from)

        if self.filter_clauses:
            expression = self._build_filter_clauses_expression(
                self.filter_clauses, expression=expression
            )

        if self._order_by:
            expression = self._build_order_by_expression(self._order_by, expression=expression)

        if self.limit_count:
            expression = expression.limit(self.limit_count)

        if self._offset:
            expression = expression.offset(self._offset)

        if self._group_by:
            expression = self._build_group_by_expression(self._group_by, expression=expression)

        if self.distinct_on:
            expression = self._build_select_distinct(self.distinct_on, expression=expression)

        setattr(self, "_expression", expression)
        return expression

    def _filter_query(self, exclude: bool = False, **kwargs):
        from saffier.models import Model

        clauses = []
        filter_clauses = self.filter_clauses
        select_related = list(self._select_related)

        if kwargs.get("pk"):
            pk_name = self.model_class.pkname
            kwargs[pk_name] = kwargs.pop("pk")

        for key, value in kwargs.items():
            if "__" in key:
                parts = key.split("__")

                # Determine if we should treat the final part as a
                # filter operator or as a related field.
                if parts[-1] in FILTER_OPERATORS:
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
                        model_class = model_class.fields[part].target

                column = model_class.table.columns[field_name]

            else:
                op = "exact"
                column = self.table.columns[key]

            # Map the operation code onto SQLAlchemy's ColumnElement
            # https://docs.sqlalchemy.org/en/latest/core/sqlelement.html#sqlalchemy.sql.expression.ColumnElement
            op_attr = FILTER_OPERATORS[op]
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
            filter_clauses.append(sqlalchemy.not_(sqlalchemy.sql.and_(*clauses)))
        else:
            filter_clauses += clauses

        return self.__class__(
            model_class=self.model_class,
            filter_clauses=filter_clauses,
            select_related=select_related,
            limit_count=self.limit_count,
            limit_offset=self._offset,
            order_by=self._order_by,
        )

    def _validate_kwargs(self, **kwargs):
        fields = self.model_class.fields
        validator = Schema(fields={key: value.validator for key, value in fields.items()})
        kwargs = validator.validate(kwargs)
        for key, value in fields.items():
            if value.validator.read_only and value.validator.has_default():
                kwargs[key] = value.validator.get_default_value()
        return kwargs

    def _prepare_order_by(self, order_by: str):
        reverse = order_by.startswith("-")
        order_by = order_by.lstrip("-")
        order_col = self.table.columns[order_by]
        return order_col.desc() if reverse else order_col

    def _prepare_group_by(self, group_by: str):
        group_by = group_by.lstrip("-")
        group_col = self.table.columns[group_by]
        return group_col

    def _prepare_fields_for_distinct(self, distinct_on: str):
        distinct_on = self.table.columns[distinct_on]
        return distinct_on

    def _clone(self) -> "QuerySet[SaffierModel]":
        queryset = self.__class__.__new__(self.__class__)
        queryset.model_class = self.model_class
        queryset.filter_clauses = copy.copy(self.filter_clauses)
        queryset.limit_count = self.limit_count
        queryset._select_related = copy.copy(self._select_related)
        queryset._offset = self._offset
        queryset._order_by = copy.copy(self._order_by)
        queryset._group_by = copy.copy(self._group_by)
        queryset.distinct_on = copy.copy(self.distinct_on)
        queryset._expression = self._expression
        return queryset


class QuerySet(BaseQuerySet, AwaitableQuery[SaffierModel]):
    """
    QuerySet object used for query retrieving.
    """

    ESCAPE_CHARACTERS = ["%", "_"]

    def __init__(
        self,
        model_class=None,
        filter_clauses=None,
        select_related=None,
        limit_count=None,
        limit_offset=None,
        order_by=None,
        group_by=None,
        distinct_on=None,
    ):
        super().__init__(model_class=model_class)
        self.model_class = model_class
        self.filter_clauses = [] if filter_clauses is None else filter_clauses
        self.limit_count = limit_count
        self._select_related = [] if select_related is None else select_related
        self._offset = limit_offset
        self._order_by = [] if order_by is None else order_by
        self._group_by = [] if group_by is None else group_by
        self.distinct_on = [] if distinct_on is None else distinct_on
        self._expression = None

    def __get__(self, instance, owner):
        return self.__class__(model_class=owner)

    @property
    def sql(self):
        return str(self._expression)

    @sql.setter
    def sql(self, value):
        setattr(self, "_expression", value)

    async def __aiter__(self) -> typing.AsyncIterator[SaffierModel]:
        for value in await self:
            yield value

    def _set_query_expression(self, expression: typing.Any) -> None:
        """
        Sets the value of the sql property to the expression used.
        """
        self.sql = expression
        self.model_class.raw_query = self.sql

    def _filter_or_exclude(
        self,
        clause: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        exclude: bool = False,
        **kwargs: DictAny,
    ):
        """
        Filters or excludes a given clause for a specific QuerySet.
        """
        queryset = self._clone()
        if clause is None:
            if not exclude:
                return queryset._filter_query(**kwargs)
            return queryset._filter_query(exclude=exclude, **kwargs)

        queryset.filter_clauses.append(clause)
        return queryset

    def filter(
        self,
        clause: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        **kwargs: typing.Any,
    ):
        """
        Filters the QuerySet by the given kwargs and clause.
        """
        return self._filter_or_exclude(clause=clause, **kwargs)

    def exclude(
        self,
        clause: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        **kwargs: typing.Any,
    ):
        """
        Exactly the same as the filter but for the exclude.
        """
        return self._filter_or_exclude(clause=clause, exclude=True, **kwargs)

    def search(self, term: typing.Any):
        """
        Broader way of searching for a given term
        """
        queryset = self._clone()
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

    def order_by(self, *order_by: str):
        """
        Returns a QuerySet ordered by the given fields.
        """
        queryset = self._clone()
        queryset._order_by = order_by
        return queryset

    def limit(self, limit_count: int):
        """
        Returns a QuerySet limited by.
        """
        queryset = self._clone()
        queryset.limit_count = limit_count
        return queryset

    def offset(self, offset: int):
        """
        Returns a Queryset limited by the offset.
        """
        queryset = self._clone()
        queryset._offset = offset
        return queryset

    def group_by(self, *group_by: str):
        """
        Returns the values grouped by the given fields.
        """
        queryset = self._clone()
        queryset._group_by = group_by
        return queryset

    def distinct(self, *distinct_on: str):
        """
        Returns a queryset with distinct results.
        """
        queryset = self._clone()
        queryset.distinct_on = distinct_on
        return queryset

    def select_related(self, related):
        """Caches teh already selected fields of a query avoiding multiple database calls"""
        queryset = self._clone()
        if not isinstance(related, (list, tuple)):
            related = [related]

        related = list(self._select_related) + related
        queryset._select_related = related
        return queryset

    async def exists(self) -> bool:
        """
        Returns a boolean indicating if a record exists or not.
        """
        expression = self._build_select()
        expression = sqlalchemy.exists(expression).select()
        self._set_query_expression(expression)
        return await self.database.fetch_val(expression)

    async def count(self) -> int:
        """
        Returns an indicating the total records.
        """
        expression = self._build_select().alias("subquery_for_count")
        expression = sqlalchemy.func.count().select().select_from(expression)
        self._set_query_expression(expression)
        return await self.database.fetch_val(expression)

    async def get_or_none(self, **kwargs):
        """
        Fetch one object matching the parameters or returns None.
        """
        queryset = self.filter(**kwargs)
        expression = queryset._build_select().limit(2)
        self._set_query_expression(expression)
        rows = await self.database.fetch_all(expression)

        if not rows:
            return None
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        return self.model_class._from_row(rows[0], select_related=self._select_related)

    async def all(self, **kwargs):
        """
        Returns the queryset records based on specific filters
        """
        queryset = self._clone()
        if kwargs:
            return await queryset.filter(**kwargs).all()

        expression = queryset._build_select()
        self._set_query_expression(expression)

        rows = await queryset.database.fetch_all(expression)

        # Attach the raw query to the object
        queryset.model_class.raw_query = self.sql
        return [
            queryset.model_class._from_row(row, select_related=self._select_related)
            for row in rows
        ]

    async def get(self, **kwargs):
        """
        Returns a single record based on the given kwargs.
        """
        if kwargs:
            return await self.filter(**kwargs).get()

        expression = self._build_select().limit(2)
        rows = await self.database.fetch_all(expression)
        self._set_query_expression(expression)

        if not rows:
            raise DoesNotFound()
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        return self.model_class._from_row(rows[0], select_related=self._select_related)

    async def first(self, **kwargs):
        """
        Returns the first record of a given queryset.
        """
        queryset = self._clone()
        if kwargs:
            return await queryset.filter(**kwargs).order_by("id").get()

        rows = await queryset.limit(1).order_by("id").all()
        if rows:
            return rows[0]

    async def last(self, **kwargs):
        """
        Returns the last record of a given queryset.
        """
        queryset = self._clone()
        if kwargs:
            return await queryset.filter(**kwargs).order_by("-id").get()

        rows = await queryset.order_by("-id").all()
        if rows:
            return rows[0]

    async def create(self, **kwargs):
        """
        Creates a record in a specific table.
        """
        kwargs = self._validate_kwargs(**kwargs)
        instance = self.model_class(**kwargs)
        expression = self.table.insert().values(**kwargs)
        self._set_query_expression(expression)

        if self.pkname not in kwargs:
            instance.pk = await self.database.execute(expression)
        else:
            await self.database.execute(expression)

        return instance

    async def bulk_create(self, objs: typing.List[typing.Dict]) -> None:
        """
        Bulk creates records in a table
        """
        new_objs = [self._validate_kwargs(**obj) for obj in objs]

        expression = self.table.insert().values(new_objs)
        self._set_query_expression(expression)
        await self.database.execute(expression)

    async def bulk_update(self, objs: typing.List[SaffierModel], fields: typing.List[str]) -> None:
        """
        Bulk updates records in a table.

        A similar solution was suggested here: https://github.com/encode/orm/pull/148

        It is thought to be a clean approach to a simple problem so it was added here and
        refactored to be compatible with Saffier.
        """
        new_fields = {}
        for key, field in self.model_class.fields.items():
            if key in fields:
                new_fields[key] = field.validator

        validator = Schema(fields=new_fields)

        new_objs = []
        for obj in objs:
            new_obj = {}
            for key, value in obj.__dict__.items():
                if key in fields:
                    new_obj[key] = self._resolve_value(value)
            new_objs.append(new_obj)

        new_objs = [
            self._update_auto_now_fields(validator.validate(obj), self.model_class.fields)
            for obj in new_objs
        ]

        pk = getattr(self.table.c, self.pkname)
        expression = self.table.update().where(pk == sqlalchemy.bindparam(self.pkname))
        kwargs = {field: sqlalchemy.bindparam(field) for obj in new_objs for field in obj.keys()}
        pks = [{self.pkname: getattr(obj, self.pkname)} for obj in objs]

        query_list = []
        for pk, value in zip(pks, new_objs):
            query_list.append({**pk, **value})

        expression = expression.values(kwargs)
        self._set_query_expression(expression)
        await self.database.execute_many(str(expression), query_list)

    async def delete(self) -> None:
        expression = self.table.delete()
        for filter_clause in self.filter_clauses:
            expression = expression.where(filter_clause)

        self._set_query_expression(expression)
        await self.database.execute(expression)

    async def update(self, **kwargs) -> None:
        """
        Updates a record in a specific table with the given kwargs.
        """
        fields = {
            key: field.validator for key, field in self.model_class.fields.items() if key in kwargs
        }

        validator = Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.validate(kwargs), self.model_class.fields)
        expression = self.table.update().values(**kwargs)

        for filter_clause in self.filter_clauses:
            expression = expression.where(filter_clause)

        self._set_query_expression(expression)
        await self.database.execute(expression)

    async def get_or_create(
        self, defaults: typing.Dict[str, typing.Any], **kwargs
    ) -> typing.Tuple[typing.Any, bool]:
        """
        Creates a record in a specific table or updates if already exists.
        """
        try:
            instance = await self.get(**kwargs)
            return instance, False
        except DoesNotFound:
            kwargs.update(defaults)
            instance = await self.create(**kwargs)
            return instance, True

    async def update_or_create(
        self, defaults: typing.Dict[str, typing.Any], **kwargs
    ) -> typing.Tuple[typing.Any, bool]:
        """
        Updates a record in a specific table or creates a new one.
        """
        try:
            instance = await self.get(**kwargs)
            await instance.update(**defaults)
            return instance, False
        except DoesNotFound:
            kwargs.update(defaults)
            instance = await self.create(**kwargs)
            return instance, True

    async def _execute(self) -> typing.List[SaffierModel]:
        return await self.all()

    def __await__(self) -> typing.Generator[typing.Any, None, typing.List[SaffierModel]]:
        return self._execute().__await__()
