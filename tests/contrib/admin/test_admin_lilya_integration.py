from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient, Response
from lilya.apps import Lilya
from lilya.middleware import DefineMiddleware
from lilya.middleware.sessions import SessionMiddleware
from lilya.routing import Include

import saffier
from saffier.contrib.admin import AdminConfig, create_admin_app
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class AdminPortalUser(saffier.Model):
    """Model used by real Lilya admin integration tests.

    The fields intentionally cover required strings, boolean defaults, and an
    auto-incrementing primary key so create, edit, table rendering, schema
    generation, and primary-key URL encoding all run through real Saffier model
    behavior.
    """

    name = saffier.CharField(max_length=100)
    active = saffier.BooleanField(default=False)

    class Meta:
        """Bind the test model to a dedicated admin integration table.

        A unique table name keeps this test module independent from the other
        admin service tests that also define user-like models.
        """

        registry = models
        tablename = "admin_portal_users"


class AdminPortalLocked(saffier.Model):
    """Model that remains browsable but cannot be created through admin.

    ``Meta.no_admin_create`` is the key branch under test: the model should
    appear in dashboards and schema responses, while create links and create
    POSTs are blocked.
    """

    name = saffier.CharField(max_length=100)

    class Meta:
        """Bind the locked test model and disable admin creation.

        The table is real so list/detail routes can still render and counts can
        be queried while create behavior is refused by the admin service.
        """

        registry = models
        tablename = "admin_portal_locked"
        no_admin_create = True


@pytest.fixture(autouse=True, scope="module")
async def create_test_database() -> AsyncGenerator[None, None]:
    """Create and drop the real tables used by the Lilya admin tests.

    The tests exercise actual Saffier persistence through HTTP requests. Module
    setup therefore creates the SQL tables once, while per-test rollback keeps
    each stateful flow isolated.

    Yields:
        None: Control to the test module while tables exist.
    """
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection() -> AsyncGenerator[None, None]:
    """Wrap each integration test in Saffier's rollback test transaction.

    The ASGI app uses the same registry/database objects as the direct
    assertions. Rolling back after every test keeps HTTP-created rows from
    leaking into the next scenario.

    Yields:
        None: Control to a single test while rollback is active.
    """
    with database.force_rollback():
        async with database:
            yield


def _make_admin_app(
    *,
    mount_path: str = "/admin",
    public_prefix: str = "/admin",
    auth_password: str | None = None,
) -> Lilya:
    """Create a real Lilya app with Saffier admin mounted inside it.

    The parent ``Include`` installs Lilya's ``SessionMiddleware`` because
    Saffier's admin child app installs ``SessionContextMiddleware`` for flash
    messages and recent-model state. ``public_prefix`` can intentionally differ
    from ``mount_path`` to model reverse proxies such as nginx.

    Args:
        mount_path: Internal ASGI path where the admin child app is mounted.
        public_prefix: Public URL prefix used for generated admin links and
            redirects.
        auth_password: Optional password enabling real BasicAuth middleware.

    Returns:
        Lilya: Parent ASGI app ready for ``httpx.ASGITransport``.
    """
    config = AdminConfig(admin_prefix_url=public_prefix)
    admin_app = create_admin_app(
        registry=models,
        config=config,
        auth_username="root",
        auth_password=auth_password,
    )
    return Lilya(
        routes=[
            Include(
                mount_path,
                app=admin_app,
                middleware=[
                    DefineMiddleware(
                        SessionMiddleware,
                        secret_key=config.secret_key,
                        session_cookie="admin_session",
                    )
                ],
            )
        ]
    )


def _encoded_pk_from_location(response: Response) -> str:
    """Extract the encoded primary key from an admin redirect response.

    Create redirects end at ``/models/{Model}/{encoded_pk}``. Pulling the key
    from the real response location lets the test assert both URL generation and
    database state for the same object.

    Args:
        response: HTTP response returned by a create or edit request.

    Returns:
        str: Encoded admin primary-key payload.
    """
    return unquote(response.headers["location"].rstrip("/").rsplit("/", 1)[-1])


def _decode_pk(encoded_pk: str) -> dict[str, Any]:
    """Decode an admin primary-key payload for direct DB assertions.

    Args:
        encoded_pk: URL-safe base64 payload produced by ``AdminSite``.

    Returns:
        dict[str, Any]: Primary-key lookup dictionary.
    """
    return json.loads(urlsafe_b64decode(encoded_pk))


@pytest.fixture()
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an HTTP client mounted against the real admin ASGI app.

    The default fixture uses the same internal and public ``/admin`` prefix,
    matching the common local development setup while still exercising the
    configured-prefix URL path.

    Yields:
        AsyncClient: HTTPX client bound to the Lilya app.
    """
    app = _make_admin_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_lilya_admin_renders_assets_and_schema(admin_client: AsyncClient) -> None:
    """Verify the real admin pages render the Edgy-grade UI dependencies.

    The dashboard and create page should include Tailwind, Font Awesome, and
    JSONEditor assets from the shared base templates. The schema endpoints must
    expose Saffier's compact admin metadata, including create permissions.
    """
    dashboard = await admin_client.get("/admin/")
    assert dashboard.status_code == 200
    assert "https://cdn.tailwindcss.com" in dashboard.text
    assert "@fortawesome/fontawesome-free" in dashboard.text
    assert "@json-editor/json-editor" in dashboard.text
    assert "AdminPortalUser" in dashboard.text
    assert "AdminPortalLocked" in dashboard.text

    create_page = await admin_client.get("/admin/models/AdminPortalUser/create")
    assert create_page.status_code == 200
    assert 'id="editor_holder"' in create_page.text
    assert "new JSONEditor" in create_page.text
    assert "AdminPortalUserCreateAdminMarshall" in create_page.text

    user_schema = await admin_client.get("/admin/models/AdminPortalUser/json")
    assert user_schema.status_code == 200
    assert user_schema.json()["can_create"] is True

    locked_schema = await admin_client.get("/admin/models/AdminPortalLocked/schema")
    assert locked_schema.status_code == 200
    assert locked_schema.json()["can_create"] is False


async def test_lilya_admin_create_edit_delete_persists_state(
    admin_client: AsyncClient,
) -> None:
    """Prove the real HTML admin flow changes database state.

    The test posts JSONEditor payloads through create and edit routes, verifies
    the redirected object page, checks direct ORM state after each mutation, and
    confirms delete removes the persisted object.
    """
    create_response = await admin_client.post(
        "/admin/models/AdminPortalUser/create",
        data={"editor_data": json.dumps({"name": "alice", "active": True})},
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    assert create_response.headers["location"].startswith("/admin/models/AdminPortalUser/")

    encoded_pk = _encoded_pk_from_location(create_response)
    created = await AdminPortalUser.query.get(**_decode_pk(encoded_pk))
    assert created.name == "alice"
    assert created.active is True

    detail_response = await admin_client.get(create_response.headers["location"])
    assert detail_response.status_code == 200
    assert "alice" in detail_response.text

    edit_response = await admin_client.post(
        f"/admin/models/AdminPortalUser/{encoded_pk}/edit",
        data={"editor_data": json.dumps({"name": "alice-updated", "active": False})},
        follow_redirects=False,
    )
    assert edit_response.status_code == 303
    updated = await AdminPortalUser.query.get(**_decode_pk(encoded_pk))
    assert updated.name == "alice-updated"
    assert updated.active is False

    updated_detail = await admin_client.get(edit_response.headers["location"])
    assert updated_detail.status_code == 200
    assert "alice-updated" in updated_detail.text

    delete_response = await admin_client.post(
        f"/admin/models/AdminPortalUser/{encoded_pk}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == "/admin/models/AdminPortalUser"
    assert await AdminPortalUser.query.count() == 0


async def test_lilya_admin_blocks_no_admin_create(admin_client: AsyncClient) -> None:
    """Ensure ``Meta.no_admin_create`` is enforced in UI and POST paths.

    The locked model remains visible in the admin table, but create links should
    not be rendered and both GET and POST create requests should redirect back
    to the model list without persisting data.
    """
    listing = await admin_client.get("/admin/models/AdminPortalLocked")
    assert listing.status_code == 200
    assert "/admin/models/AdminPortalLocked/create" not in listing.text

    create_get = await admin_client.get(
        "/admin/models/AdminPortalLocked/create",
        follow_redirects=False,
    )
    assert create_get.status_code == 303
    assert create_get.headers["location"] == "/admin/models/AdminPortalLocked"

    create_post = await admin_client.post(
        "/admin/models/AdminPortalLocked/create",
        data={"editor_data": json.dumps({"name": "blocked"})},
        follow_redirects=False,
    )
    assert create_post.status_code == 303
    assert create_post.headers["location"] == "/admin/models/AdminPortalLocked"
    assert await AdminPortalLocked.query.count() == 0


async def test_lilya_admin_supports_nginx_style_public_prefix() -> None:
    """Verify public admin links can differ from the internal mount path.

    A reverse proxy may send traffic to ``/internal-admin`` while exposing the
    admin publicly at ``/proxy/saffier/admin``. The rendered links and redirects
    must use the configured public prefix so browsers never navigate to the
    internal upstream route.
    """
    app = _make_admin_app(
        mount_path="/internal-admin",
        public_prefix="/proxy/saffier/admin",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dashboard = await client.get("/internal-admin/")
        assert dashboard.status_code == 200
        assert "/proxy/saffier/admin/models/AdminPortalUser" in dashboard.text

        create_page = await client.get("/internal-admin/models/AdminPortalUser/create")
        assert create_page.status_code == 200
        assert "/proxy/saffier/admin/models/AdminPortalUser" in create_page.text

        create_response = await client.post(
            "/internal-admin/models/AdminPortalUser/create",
            data={"editor_data": json.dumps({"name": "proxied"})},
            follow_redirects=False,
        )
        assert create_response.status_code == 303
        assert create_response.headers["location"].startswith(
            "/proxy/saffier/admin/models/AdminPortalUser/"
        )


async def test_lilya_admin_basic_auth_runs_in_real_asgi_stack() -> None:
    """Verify optional BasicAuth protects the real Lilya admin mount.

    This covers the middleware order used by ``create_admin_app`` together with
    the parent session middleware required by Lilya session context. Missing or
    invalid credentials should receive the standard challenge, while valid
    credentials can render the dashboard.
    """
    app = _make_admin_app(auth_password="secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/admin/")
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["www-authenticate"].startswith("Basic")

        invalid = await client.get("/admin/", auth=("root", "bad"))
        assert invalid.status_code == 401

        authenticated = await client.get("/admin/", auth=("root", "secret"))
        assert authenticated.status_code == 200
        assert "Saffier Admin Dashboard" in authenticated.text
