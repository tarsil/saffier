import typing

import sqlalchemy

from saffier.constants import FILTER_OPERATORS
from saffier.core.schemas import Schema
from saffier.exceptions import DoesNotFound, MultipleObjectsReturned
from saffier.fields import CharField, TextField
from saffier.utils import ModelUtil


class BaseManager(ModelUtil):
    def get_queryset(self):
        """
        Return a new QuerySet object.
        The subclasses can override this behaviour to manage the custom Manager.
        """
        ...


class QuerySet(ModelUtil):
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
    ):
        self.model_class = model_class
        self.filter_clauses = [] if filter_clauses is None else filter_clauses
        self._select_related = [] if select_related is None else select_related
        self.limit_count = limit_count
        self._offset = limit_offset
        self._order_by = [] if order_by is None else order_by

    def __get__(self, instance, owner):
        return self.__class__(model_class=owner)

    @property
    def database(self):
        return self.model_class.registry.database

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

    def _build_select(self):
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

        expression = sqlalchemy.sql.select(tables)
        expression = expression.select_from(select_from)

        if self.filter_clauses:
            if len(self.filter_clauses) == 1:
                clause = self.filter_clauses[0]
            else:
                clause = sqlalchemy.sql.and_(*self.filter_clauses)
            expression = expression.where(clause)

        if self._order_by:
            order_by = list(map(self._prepare_order_by, self._order_by))
            expression = expression.order_by(*order_by)

        if self.limit_count:
            expression = expression.limit(self.limit_count)

        if self._offset:
            expression = expression.offset(self._offset)

        return expression

    def filter(
        self,
        clause: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        **kwargs: typing.Any,
    ):
        if clause is not None:
            self.filter_clauses.append(clause)
            return self
        else:
            return self._filter_query(**kwargs)

    def exclude(
        self,
        clause: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        **kwargs: typing.Any,
    ):
        if clause is not None:
            self.filter_clauses.append(clause)
            return self
        else:
            return self._filter_query(_exclude=True, **kwargs)

    def _filter_query(self, _exclude: bool = False, **kwargs):
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

        if _exclude:
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

    def search(self, term: typing.Any):
        if not term:
            return self

        filter_clauses = list(self.filter_clauses)
        value = f"%{term}%"

        search_fields = [
            name
            for name, field in self.model_class.fields.items()
            if isinstance(field, (CharField, TextField))
        ]
        search_clauses = [self.table.columns[name].ilike(value) for name in search_fields]

        if len(search_clauses) > 1:
            filter_clauses.append(sqlalchemy.sql.or_(*search_clauses))
        else:
            filter_clauses.extend(search_clauses)

        return self.__class__(
            model_class=self.model_class,
            filter_clauses=filter_clauses,
            select_related=self._select_related,
            limit_count=self.limit_count,
            limit_offset=self._offset,
            order_by=self._order_by,
        )

    def order_by(self, *order_by):
        return self.__class__(
            model_class=self.model_class,
            filter_clauses=self.filter_clauses,
            select_related=self._select_related,
            limit_count=self.limit_count,
            limit_offset=self._offset,
            order_by=order_by,
        )

    def select_related(self, related):
        if not isinstance(related, (list, tuple)):
            related = [related]

        related = list(self._select_related) + related
        return self.__class__(
            model_class=self.model_class,
            filter_clauses=self.filter_clauses,
            select_related=related,
            limit_count=self.limit_count,
            limit_offset=self._offset,
            order_by=self._order_by,
        )

    async def exists(self) -> bool:
        expression = self._build_select()
        expression = sqlalchemy.exists(expression).select()
        return await self.database.fetch_val(expression)

    def limit(self, limit_count: int):
        return self.__class__(
            model_class=self.model_class,
            filter_clauses=self.filter_clauses,
            select_related=self._select_related,
            limit_count=limit_count,
            limit_offset=self._offset,
            order_by=self._order_by,
        )

    def limit_offset(self, offset: int):
        return self.__class__(
            model_class=self.model_class,
            filter_clauses=self.filter_clauses,
            select_related=self._select_related,
            limit_count=self.limit_count,
            limit_offset=offset,
            order_by=self._order_by,
        )

    async def count(self) -> int:
        expression = self._build_select().alias("subquery_for_count")
        expression = sqlalchemy.func.count().select().select_from(expression)
        return await self.database.fetch_val(expression)

    async def all(self, **kwargs):
        if kwargs:
            return await self.filter(**kwargs).all()

        expression = self._build_select()
        rows = await self.database.fetch_all(expression)
        return [
            self.model_class._from_row(row, select_related=self._select_related) for row in rows
        ]

    async def get(self, **kwargs):
        if kwargs:
            return await self.filter(**kwargs).get()

        expression = self._build_select().limit(2)
        rows = await self.database.fetch_all(expression)

        if not rows:
            raise DoesNotFound()
        if len(rows) > 1:
            raise MultipleObjectsReturned()
        return self.model_class._from_row(rows[0], select_related=self._select_related)

    async def first(self, **kwargs):
        if kwargs:
            return await self.filter(**kwargs).first()

        rows = await self.limit(1).all()
        if rows:
            return rows[0]

    async def last(self, **kwargs):
        if kwargs:
            return await self.filter(**kwargs).last()

        rows = await self.all()
        if rows:
            return rows[-1]

    def _validate_kwargs(self, **kwargs):
        fields = self.model_class.fields
        validator = Schema(fields={key: value.validator for key, value in fields.items()})
        kwargs = validator.validate(kwargs)
        for key, value in fields.items():
            if value.validator.read_only and value.validator.has_default():
                kwargs[key] = value.validator.get_default_value()
        return kwargs

    async def create(self, **kwargs):
        kwargs = self._validate_kwargs(**kwargs)
        instance = self.model_class(**kwargs)
        expression = self.table.insert().values(**kwargs)

        if self.pkname not in kwargs:
            instance.pk = await self.database.execute(expression)
        else:
            await self.database.execute(expression)

        return instance

    async def bulk_create(self, objs: typing.List[typing.Dict]) -> None:
        new_objs = [self._validate_kwargs(**obj) for obj in objs]

        expression = self.table.insert().values(new_objs)
        await self.database.execute(expression)

    async def delete(self) -> None:
        expression = self.table.delete()
        for filter_clause in self.filter_clauses:
            expression = expression.where(filter_clause)

        await self.database.execute(expression)

    async def update(self, **kwargs) -> None:
        fields = {
            key: field.validator for key, field in self.model_class.fields.items() if key in kwargs
        }
        validator = Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.validate(kwargs), self.model_class.fields)
        expr = self.table.update().values(**kwargs)

        for filter_clause in self.filter_clauses:
            expr = expr.where(filter_clause)

        await self.database.execute(expr)

    async def get_or_create(
        self, defaults: typing.Dict[str, typing.Any], **kwargs
    ) -> typing.Tuple[typing.Any, bool]:
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
        try:
            instance = await self.get(**kwargs)
            await instance.update(**defaults)
            return instance, False
        except DoesNotFound:
            kwargs.update(defaults)
            instance = await self.create(**kwargs)
            return instance, True

    def _prepare_order_by(self, order_by: str):
        reverse = order_by.startswith("-")
        order_by = order_by.lstrip("-")
        order_col = self.table.columns[order_by]
        return order_col.desc() if reverse else order_col
