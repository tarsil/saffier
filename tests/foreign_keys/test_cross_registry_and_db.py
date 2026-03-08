import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL, full_isolation=False)
database2 = Database(DATABASE_ALTERNATIVE_URL, full_isolation=False)
modelsa = saffier.Registry(database=database)
modelsb = saffier.Registry(database=database2)
modelsc = saffier.Registry(database=database)


class ObjectA(saffier.StrictModel):
    self_ref = saffier.ForeignKey("ObjectA", on_delete=saffier.CASCADE, null=True)
    c = saffier.ForeignKey(
        "ObjectC",
        target_registry=modelsc,
        on_delete=saffier.CASCADE,
        null=True,
    )

    class Meta:
        registry = modelsa
        tablename = "cross_registry_object_a"


class ObjectB(saffier.StrictModel):
    a = saffier.ForeignKey(ObjectA, on_delete=saffier.CASCADE, null=True)

    class Meta:
        registry = modelsb
        tablename = "cross_registry_object_b"


class ObjectC(saffier.StrictModel):
    b = saffier.ForeignKey(ObjectB, on_delete=saffier.CASCADE, null=True)

    class Meta:
        registry = modelsc
        tablename = "cross_registry_object_c"


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with database, database2:
        await modelsc.create_all()
        await modelsb.create_all()
        await modelsa.create_all()
        yield
        await modelsa.drop_all()
        await modelsc.drop_all()
        await modelsb.drop_all()


async def test_specs():
    assert not ObjectA.meta.fields["self_ref"].is_cross_db()
    assert not ObjectA.meta.fields["c"].is_cross_db()
    assert ObjectB.meta.fields["a"].is_cross_db()
    assert ObjectC.meta.fields["b"].is_cross_db()


async def test_empty_fk():
    obj = await ObjectA.query.create()
    assert obj.self_ref is None
    assert obj.c is None
    obj = await ObjectB.query.create(a={})
    assert obj.a.self_ref is None
    assert obj.a.c is None


async def test_create():
    obj = await ObjectC.query.create(b={"a": {"c": None, "self_ref": None}})
    obj.b.a.self_ref = obj.b.a
    obj.b.a.c = obj
    await obj.b.a.save()
    loaded = await ObjectC.query.get(pk=obj.pk)
    assert loaded.id == obj.id
    assert loaded.b.id == obj.b.id
    assert loaded.b.a.meta.registry is modelsa
    assert loaded.b.a.id == obj.b.a.id
    assert loaded.b.a.c == obj


async def test_query():
    obj = await ObjectC.query.create(b={"a": {"c": None, "self_ref": None}})
    obj.b.a.c = obj
    obj.b.a.self_ref = obj.b.a
    await obj.b.a.save()
    objs = await ObjectC.query.filter(b__a__c=obj)
    assert objs[0] == obj
