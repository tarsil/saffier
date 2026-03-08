from typing import Any

import pytest
import sqlalchemy

import saffier
from saffier.core.db.fields._internal import Any as AnyField
from saffier.core.db.querysets.clauses import and_
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class MultiColumnField(saffier.CharField):
    def get_validator(self, **kwargs: Any) -> AnyField:
        return AnyField(**kwargs)

    def operator_to_clause(
        self, field_name: str, operator: str, table: sqlalchemy.Table, value: Any
    ) -> Any:
        return and_(
            super().operator_to_clause(field_name, operator, table, value["normal"]),
            super().operator_to_clause(f"{field_name}_inner", operator, table, value["inner"]),
        )

    def get_columns(self, name: str) -> list[sqlalchemy.Column]:
        return [
            super().get_column(name),
            super().get_column(f"{name}_inner"),
        ]

    def _normalize(self, name: str, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            return {name: value, f"{name}_inner": value}
        return {name: value["normal"], f"{name}_inner": value["inner"]}

    def clean(self, name: str, value: Any, *, for_query: bool = False) -> dict[str, Any]:
        if for_query:
            normalized = self._normalize("normal", value)
            return {
                name: {
                    "normal": normalized["normal"],
                    "inner": normalized["normal_inner"],
                }
            }
        return self._normalize(name, value)

    def modify_input(self, name: str, kwargs: dict[str, Any]) -> None:
        if name not in kwargs and f"{name}_inner" not in kwargs:
            return
        normal = kwargs.pop(name, None)
        if isinstance(normal, dict):
            kwargs[name] = normal
            return
        kwargs[name] = {
            "normal": normal,
            "inner": kwargs.pop(f"{name}_inner", normal),
        }

    def set_value(self, instance: Any, field_name: str, value: Any) -> None:
        payload = self.clean(field_name, value)
        instance.__dict__[field_name] = {
            "normal": payload[field_name],
            "inner": payload[f"{field_name}_inner"],
        }


class MyModel(saffier.StrictModel):
    multi = MultiColumnField(max_length=255)

    class Meta:
        registry = models
        tablename = "field_multi_columns"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_basic_model():
    obj = MyModel(multi="edgy")
    assert obj.multi["normal"] == "edgy"
    assert obj.multi["inner"] == "edgy"


async def test_create_and_assign():
    obj = await MyModel.query.create(multi="edgy", multi_inner="edgytoo")
    assert obj.multi["normal"] == "edgy"
    assert obj.multi["inner"] == "edgytoo"
    assert hasattr(MyModel.table.columns, "multi_inner")

    assert await MyModel.query.filter(multi__exact={"normal": "edgy", "inner": "edgytoo"}).exists()
    assert await MyModel.query.filter(multi__like={"normal": "edgy", "inner": "edgytoo"}).exists()
    assert await MyModel.query.filter(multi__startswith="edgy").exists()

    obj.multi = "test"
    assert obj.multi["normal"] == "test"
    assert obj.multi["inner"] == "test"
    await obj.save()
    assert await MyModel.query.filter(MyModel.table.columns.multi_inner == "test").exists()
    assert await MyModel.query.filter(multi="test").exists()

    obj.multi = {"normal": "edgy", "inner": "foo"}
    await obj.save()
    assert await MyModel.query.filter(MyModel.table.columns.multi_inner == "foo").exists()
    assert obj.multi["normal"] == "edgy"


async def test_indb():
    obj = await MyModel.query.create(multi="edgy", multi_inner="edgytoo")
    await MyModel.query.update(
        multi={
            "normal": MyModel.table.c.multi + "foo",
            "inner": MyModel.table.c.multi_inner + "foo",
        }
    )
    await obj.load()
    assert obj.multi["normal"] == "edgyfoo"
    assert obj.multi["inner"] == "edgytoofoo"
