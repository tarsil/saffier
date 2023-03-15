from typing import Any

import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.db.connection import Database
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
        self._metadata = sqlalchemy.MetaData()

    @property
    def metadata(self) -> Any:
        for model_class in self.models.values():
            model_class.build_table()
        return self._metadata

    def _get_database_url(self) -> str:
        url = self.database.url
        if not url.driver:
            if url.dialect == "postgressql":
                url = url.replace(driver="asyncpg")
            elif url.dialect == "mysql":
                url = url.replace(driver="aiomysql")
            elif url.dialect == "sqlite":
                url = url.replace(driver="aiosqlite")
        return str(url)

    def _get_engine(self) -> AsyncEngine:
        url = self._get_database_url()
        engine = create_async_engine(url)
        return engine

    async def create_all(self) -> None:
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as connection:
                await connection.run_sync(self.metadata.create_all)

        await engine.dispose()

    async def drop_all(self) -> None:
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as conn:
                await conn.run_sync(self.metadata.drop_all)

        await engine.dispose()
