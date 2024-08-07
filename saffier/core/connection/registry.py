from functools import cached_property
from typing import Any, Dict, Mapping, Type

import sqlalchemy
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import declarative_base as sa_declarative_base

from saffier.core.connection.database import Database
from saffier.core.connection.schemas import Schema


class Registry:
    """
    The command center for the models being generated
    for Saffier.
    """

    def __init__(self, database: Database, **kwargs: Any) -> None:
        self.database: Database = database
        self.models: Dict[str, Any] = {}
        self.reflected: Dict[str, Any] = {}
        self.db_schema = kwargs.get("schema", None)
        self.extra: Mapping[str, Type["Database"]] = kwargs.pop("extra", {})

        self.schema = Schema(registry=self)

        self._metadata = (
            sqlalchemy.MetaData(schema=self.db_schema)
            if self.db_schema is not None
            else sqlalchemy.MetaData()
        )

    @property
    def metadata(self) -> Any:
        for model_class in self.models.values():
            model_class.build(schema=self.db_schema)
        return self._metadata

    @metadata.setter
    def metadata(self, value: sqlalchemy.MetaData) -> None:
        self._metadata = value

    @cached_property
    def declarative_base(self) -> Any:
        if self.db_schema:
            metadata = sqlalchemy.MetaData(schema=self.db_schema)
        else:
            metadata = sqlalchemy.MetaData()
        return sa_declarative_base(metadata=metadata)

    @property
    def engine(self) -> AsyncEngine:
        assert self.database.engine, "database not started, no engine found."
        return self.database.engine

    @property
    def sync_engine(self) -> Engine:
        return self.engine.sync_engine

    async def create_all(self) -> None:
        if self.db_schema:
            await self.schema.create_schema(self.db_schema, True)
        async with Database(self.database, force_rollback=False) as database:
            async with database.transaction():
                await database.create_all(self.metadata)

    async def drop_all(self) -> None:
        if self.db_schema:
            await self.schema.drop_schema(self.db_schema, True, True)
        async with Database(self.database, force_rollback=False) as database:
            async with database.transaction():
                await database.drop_all(self.metadata)
