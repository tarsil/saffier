import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.db.connection import Database


class Registry(ArbitraryHashableBaseModel):
    """
    Registers a database connection object
    """

    def __init__(self, database: Database, **kwargs) -> None:
        super().__init__(**kwargs)
        assert isinstance(
            database, Database
        ), "database must be an instance of saffier.core.db.Database"
        self.database = database
        self.models = {}
        self._metadata = sqlalchemy.MetaData()

    @property
    def metadata(self):
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

    def _get_engine(self):
        url = self._get_database_url()
        engine = create_async_engine(url)
        return engine

    async def create_all(self):
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as connection:
                await connection.run_sync(self.metadata.create_all)

        await engine.dispose()

    async def drop_all(self):
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as conn:
                await conn.run_sync(self.metadata.drop_all)

        await engine.dispose()
