from collections.abc import AsyncGenerator, Coroutine
from typing import Any

import pytest
from anyio import from_thread, sleep, to_thread
from httpx import ASGITransport, AsyncClient
from lilya.types import ASGIApp, Receive, Scope, Send
from pydantic import __version__
from ravyn import Gateway, JSONResponse, Ravyn, Request, get
from ravyn.core.protocols.middleware import MiddlewareProtocol

from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin, TenantUserMixin
from saffier.core.db import fields, set_tenant
from saffier.exceptions import ObjectNotFound
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)


pytestmark = pytest.mark.anyio
pydantic_version = __version__[:3]


class Tenant(TenantMixin):
    class Meta:
        registry = models


class User(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True


class Product(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)
    user = fields.ForeignKey(User, null=True)

    class Meta:
        registry = models
        is_tenant = True


class TenantUser(TenantUserMixin):
    class Meta:
        registry = models


class TenantMiddleware(MiddlewareProtocol):
    def __init__(self, app: "ASGIApp"):
        super().__init__(app)
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> Coroutine[Any, Any, None]:
        request = Request(scope=scope, receive=receive, send=send)
        tenant_header = request.headers.get("tenant", None)

        try:
            user = await Tenant.query.get(schema_name=tenant_header)
            tenant = user.schema_name
        except ObjectNotFound:
            tenant = None

        set_tenant(tenant)
        await self.app(scope, receive, send)


@pytest.fixture(autouse=True)
async def database_session():
    set_tenant(None)
    with database.force_rollback():
        async with database:
            await models.create_all()
            yield
    await models.drop_all()
    set_tenant(None)


def blocking_function():
    from_thread.run(sleep, 0.1)


@get("/products")
async def get_products() -> JSONResponse:
    products = await Product.query.all()
    products = [product.pk for product in products]
    return JSONResponse(products)


@pytest.fixture()
def app():
    app = Ravyn(
        routes=[Gateway(handler=get_products)],
        middleware=[TenantMiddleware],
        on_startup=[database.connect],
        on_shutdown=[database.disconnect],
    )
    return app


@pytest.fixture()
def another_app():
    app = Ravyn(
        routes=[Gateway("/no-tenant", handler=get_products)],
        on_startup=[database.connect],
        on_shutdown=[database.disconnect],
    )
    return app


@pytest.fixture()
async def async_cli(another_app) -> AsyncGenerator:
    async with AsyncClient(
        transport=ASGITransport(app=another_app), base_url="http://test"
    ) as acli:
        await to_thread.run_sync(blocking_function)
        yield acli


@pytest.fixture()
async def async_client(app) -> AsyncGenerator:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await to_thread.run_sync(blocking_function)
        yield ac


async def create_data():
    """
    Creates mock data
    """
    saffier = await User.query.create(name="saffier")

    tenant_schema = "saffier_alt_tenant"
    alt_tenant = await Tenant.query.create(schema_name=tenant_schema, tenant_name="saffier-alt")
    tenant_user = await User.query.using(alt_tenant.schema_name).create(name="tenant-user")

    await TenantUser.query.create(user=tenant_user, tenant=alt_tenant)

    # Products for tenant schema
    for i in range(10):
        await Product.query.using(alt_tenant.schema_name).create(
            name=f"Product-{i}", user=tenant_user
        )

    # Products for Saffier
    for i in range(25):
        await Product.query.create(name=f"Product-{i}", user=saffier)


async def test_user_query_tenant_data(async_client, async_cli):
    await create_data()

    # Test tenant response intercepted in the middleware
    response_tenant = await async_client.get("/products", headers={"tenant": "saffier_alt_tenant"})
    assert response_tenant.status_code == 200

    assert len(response_tenant.json()) == 10

    # Test default schema response
    response_saffier = await async_client.get("/products")
    assert response_saffier.status_code == 200

    assert len(response_saffier.json()) == 25

    # Check tenant schema again
    response_tenant = await async_client.get("/products", headers={"tenant": "saffier_alt_tenant"})
    assert response_tenant.status_code == 200

    assert len(response_tenant.json()) == 10

    response = await async_cli.get("/no-tenant/products")
    assert response.status_code == 200
    assert len(response.json()) == 25
