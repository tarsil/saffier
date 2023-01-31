import typing

import databases
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from saffier.constants import FILTER_OPERATORS
from saffier.core.db import Database
from saffier.exceptions import DoesNotFound, MultipleObjectsReturned
from saffier.fields import CharField, DateField, DateTimeField, TextField
from saffier.types import DictAny
from saffier.utils import ModelUtil


class Registry(ModelUtil):
    """
    Registers a database connection object
    """

    def __init__(self, database: Database) -> None:
        assert isinstance(
            database, Database
        ), "database must be an instance of saffier.core.db.Database"
        self.database = database
        self.models: DictAny = {}
        self._metadata = sqlalchemy.MetaData()

    @property
    def metadata(self):
        for model_class in self.models.values():
            model_class.build_table()
        return self._metadata

    def _get_database_url(self) -> str:
        url = self.database.url

    def _get_engine(self):
        url = self._get_database_url()
        engine = create_async_engine(url)
        return engine

    async def create_all(self):
        engine = self._get_url_engine()

        async with self.database:
            async with engine.begin() as connection:
                await connection.run_sync(self.metadata.create_all)

        await engine.dispose()

    async def drop_all(self):
        engine = self._get_url_engine()

        async with self.database:
            async with engine.begin() as conn:
                await conn.run_sync(self.metadata.drop_all)

        await engine.dispose()
