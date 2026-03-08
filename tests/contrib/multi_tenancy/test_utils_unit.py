from __future__ import annotations

import pytest
import sqlalchemy

from saffier.contrib.multi_tenancy import utils


class _FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run_sync(self, fn):
        metadata = sqlalchemy.MetaData()
        fn(metadata)


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def begin(self):
        return _FakeConnection()

    async def dispose(self):
        self.disposed = True


class _FakeRegistry:
    def __init__(self, tenant_models):
        self.tenant_models = tenant_models
        self.engine = _FakeEngine()


class _TenantModel:
    def __init__(self, registry, name: str):
        metadata = sqlalchemy.MetaData()
        self.table = sqlalchemy.Table(name, metadata, sqlalchemy.Column("id", sqlalchemy.Integer))
        self.meta = type("Meta", (), {"registry": registry})


def test_table_schema_builds_and_caches_tables():
    registry = _FakeRegistry({})
    user = _TenantModel(registry, "users")
    product = _TenantModel(registry, "products")
    registry.tenant_models = {"User": user, "Product": product}

    users_table = utils.table_schema(user, "tenant_a")
    assert users_table.schema == "tenant_a"

    users_table_cached = utils.table_schema(user, "tenant_a")
    assert users_table is users_table_cached

    product_table = utils.table_schema(product, "tenant_a")
    assert product_table.schema == "tenant_a"
    assert product_table.name == "products"


@pytest.mark.anyio
async def test_create_tables_runs_and_disposes_engine():
    registry = _FakeRegistry({})
    user = _TenantModel(registry, "users")
    registry.tenant_models = {"User": user}

    await utils.create_tables(registry, registry.tenant_models, schema="tenant_x")
    assert registry.engine.disposed is True
