import pytest

import saffier
from saffier.exceptions import QuerySetError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL"),
    pytest.mark.skipif(database.url.dialect == "sqlite", reason="Not supported on SQLite"),
]


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            await User.query.bulk_create(
                [
                    {"name": "A", "language": "EN"},
                    {"name": "B", "language": "EN"},
                    {"name": "C", "language": "DE"},
                    {"name": "D", "language": "PT"},
                ]
            )
            yield


def _names(rows):
    return [user.name for user in rows]


async def test_union_basic_dedup_and_order_limit():
    q1 = User.query.filter(name__in=["A", "B"]).order_by("name")
    q2 = User.query.filter(name__in=["B", "C"]).order_by("name")

    union_qs = q1.union(q2).order_by("name")
    rows = await union_qs

    assert _names(rows) == ["A", "B", "C"]

    rows = await union_qs.limit(2)
    assert _names(rows) == ["A", "B"]


async def test_union_all_keeps_duplicates_and_outer_limit():
    q1 = User.query.filter(name__in=["A", "B"]).order_by("name")
    q2 = User.query.filter(name__in=["B", "C"]).order_by("name")

    queryset = q1.union_all(q2).order_by("name")
    rows = await queryset

    assert _names(rows) == ["A", "B", "B", "C"]

    rows = await queryset.limit(3)
    assert _names(rows) == ["A", "B", "B"]


async def test_intersect_basic():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["B", "C"])

    rows = await q1.intersect(q2).order_by("name")
    assert _names(rows) == ["B"]


async def test_except_basic():
    q1 = User.query.filter(name__in=["A", "B", "C"])
    q2 = User.query.filter(name__in=["B", "C"])

    rows = await q1.except_(q2).order_by("name")
    assert _names(rows) == ["A"]


async def test_outer_order_by_limit_offset_on_combined():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["C", "D"])

    combined = q1.union(q2)

    top1 = await combined.order_by("-id").limit(1)

    assert len(top1) == 1
    assert top1[0].name in {"C", "D"}

    next1 = await combined.order_by("-id").offset(1).limit(1)

    assert len(next1) == 1
    assert next1[0].name in {"A", "B", "C", "D"}


async def test_only_and_defer_propagation_across_union():
    q1 = User.query.filter(name__in=["A", "B"]).only("id", "name")
    q2 = User.query.filter(name__in=["B", "C"]).only("id", "name")

    rows = await q1.union(q2).order_by("name")
    assert _names(rows) == ["A", "B", "C"]

    data = await q1.union(q2).order_by("name").values(["id", "name"])

    assert list(data[0].keys()) == ["id", "name"]

    q3 = User.query.filter(name__in=["A", "B"]).defer("language")
    q4 = User.query.filter(name__in=["B", "C"]).defer("language")
    data = await q3.union(q4).order_by("name").values(["id", "name"])

    assert list(data[0].keys()) == ["id", "name"]


async def test_combining_requires_same_model_and_registry():
    q1 = User.query.filter(name="A")
    q2 = User.query.filter(name="B")
    _ = q1.union(q2)

    other_models = saffier.Registry(database=database)

    class Product(saffier.Model):
        id = saffier.IntegerField(primary_key=True, autoincrement=True)
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = other_models

    with pytest.raises(QuerySetError):
        _ = q1.union(Product.query.filter(name="X"))


async def test_union_three_way_chaining():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["C"])
    q3 = User.query.filter(name__in=["D"])

    rows = await q1.union(q2).union(q3).order_by("name")
    assert _names(rows) == ["A", "B", "C", "D"]


async def test_intersect_empty_result():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["C", "D"])

    rows = await q1.intersect(q2)

    assert rows == []


async def test_values_and_values_list_on_union():
    q1 = User.query.filter(name__in=["A", "B"]).only("id", "name")
    q2 = User.query.filter(name__in=["C"]).only("id", "name")

    data = await q1.union(q2).order_by("id").values(["id", "name"])

    assert isinstance(data, list) and all(isinstance(value, dict) for value in data)
    assert [value["name"] for value in data] == ["A", "B", "C"]

    names = await q1.union(q2).order_by("id").values_list(["name"], flat=True)

    assert names == ["A", "B", "C"]


async def test_exists_and_count_on_combined():
    q1 = User.query.filter(name__in=["A"])
    q2 = User.query.filter(name__in=["Z"])

    union_qs = q1.union(q2)

    assert await union_qs.exists() is True
    assert await union_qs.count() == 1

    inter_qs = q1.intersect(q2)

    assert await inter_qs.exists() is False
    assert await inter_qs.count() == 0


async def test_union_all_then_distinct_matches_union():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["B", "C"])

    names_all = _names(await q1.union_all(q2).order_by("name"))

    assert names_all == ["A", "B", "B", "C"]

    names_distinct_outer = _names(await q1.union_all(q2).distinct(True).order_by("name"))

    assert names_distinct_outer == ["A", "B", "C"]

    names_union = _names(await q1.union(q2).order_by("name"))

    assert names_union == ["A", "B", "C"]


async def test_inner_order_is_ignored_outer_order_applies():
    q1 = User.query.filter(name__in=["B", "A"]).order_by("-name")
    q2 = User.query.filter(name__in=["D", "C"]).order_by("-name")

    rows = await q1.union(q2).order_by("name")

    assert _names(rows) == ["A", "B", "C", "D"]


async def test_pagination_over_union_all_with_offset_limit():
    q1 = User.query.filter(name__in=["A", "B"])
    q2 = User.query.filter(name__in=["B", "C"])

    page1 = await q1.union_all(q2).order_by("name").limit(2)

    assert _names(page1) == ["A", "B"]

    page2 = await q1.union_all(q2).order_by("name").offset(2).limit(2)

    assert _names(page2) == ["B", "C"]


async def test_only_and_defer_mixed_across_union():
    q1 = User.query.filter(name__in=["A", "B"]).only("id", "name")
    q2 = User.query.filter(name__in=["C"]).defer("language")

    data = await q1.union(q2).order_by("name").values(["id", "name"])

    assert [value["name"] for value in data] == ["A", "B", "C"]


async def test_get_first_last_on_combined_are_stable():
    combined = User.query.filter(name__in=["A", "B"]).union(
        User.query.filter(name__in=["C", "D"])
    )

    first_row = await combined.order_by("name").first()
    assert first_row is not None
    assert first_row.name == "A"

    last_row = await combined.order_by("name").last()
    assert last_row is not None
    assert last_row.name == "D"
