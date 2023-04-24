from functools import cached_property
from typing import Any

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from saffier.conf import settings
from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.db.connection import Database
from saffier.exceptions import ImproperlyConfigured
from saffier.types import DictAny


class Registry(ArbitraryHashableBaseModel):
    """
    Registers a database connection object
    """

    def __init__(self, database: Database, **kwargs: DictAny) -> None:
        assert isinstance(
            database, Database
        ), "database must be an instance of saffier.core.db.Database"

        super().__init__(**kwargs)
        self.database = database
        self.models: DictAny = {}
        self.reflected: DictAny = {}
        self.db_schema = kwargs.get("schema", None)

        if self.db_schema:
            self._metadata = sqlalchemy.MetaData(schema=self.db_schema)
        else:
            self._metadata = sqlalchemy.MetaData()

    @property
    def metadata(self) -> Any:
        for model_class in self.models.values():
            model_class.build_table()
        return self._metadata

    def _get_database_url(self) -> str:
        url = self.database.url
        if not url.driver:
            if url.dialect in settings.postgres_dialects:
                url = url.replace(driver="asyncpg")
            elif url.dialect in settings.mysql_dialects:
                url = url.replace(driver="aiomysql")
            elif url.dialect in settings.sqlite_dialects:
                url = url.replace(driver="aiosqlite")
            elif url.dialect in settings.mssql_dialects:
                raise ImproperlyConfigured("Saffier does not support MSSQL at the moment.")
        elif url.driver in settings.mssql_drivers:
            raise ImproperlyConfigured("Saffier does not support MSSQL at the moment.")
        return str(url)

    @cached_property
    def _get_engine(self) -> AsyncEngine:
        url = self._get_database_url()
        engine = create_async_engine(url)
        return engine

    @property
    def engine(self):  # type: ignore
        return self._get_engine

    @cached_property
    def _get_sync_engine(self) -> AsyncEngine:
        url = self._get_database_url()
        engine = create_engine(url)
        return engine

    @property
    def sync_engine(self):  # type: ignore
        return self._get_sync_engine

    async def create_all(self) -> None:
        async with self.database:
            async with self.engine.begin() as connection:
                await connection.run_sync(self.metadata.create_all)

        await self.engine.dispose()

    async def drop_all(self) -> None:
        async with self.database:
            async with self.engine.begin() as conn:
                await conn.run_sync(self.metadata.drop_all)
        await self.engine.dispose()
