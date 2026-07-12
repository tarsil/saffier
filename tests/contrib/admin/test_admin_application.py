from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from saffier.contrib.admin.application import create_admin_app
from saffier.contrib.admin.config import AdminConfig
from saffier.contrib.admin.controllers import admin_not_found
from saffier.contrib.admin.exceptions import AdminModelNotFound, AdminValidationError
from saffier.contrib.pagination.base import Page
from saffier.exceptions import ObjectNotFound


class _FakeResponse:
    """Small response object used by the Lilya unit-test doubles.

    The admin handlers return Lilya response instances at runtime, but these
    route-level unit tests only need to inspect the payload, status code,
    rendered template name, and redirect URL. Keeping the fake narrow lets the
    tests focus on Saffier's route behavior while the integration tests exercise
    the real ASGI stack.
    """

    def __init__(
        self,
        payload: Any = None,
        status_code: int = 200,
        template: str | None = None,
    ) -> None:
        """Store response details that assertions inspect later.

        Args:
            payload: JSON body, template context, or redirect URL.
            status_code: HTTP status code assigned by the handler.
            template: Template name when the response came from rendering.
        """
        self.payload = payload
        self.status_code = status_code
        self.template = template
        self.url = payload if isinstance(payload, str) else None

    def json(self) -> Any:
        """Return the fake JSON payload.

        Returns:
            Any: Payload supplied to the fake JSON response factory.
        """
        return self.payload


class _FakeRoutePath:
    """Test double for ``lilya.routing.RoutePath``.

    It records the route metadata and endpoint callable so tests can invoke the
    nested admin handlers directly without running a full ASGI router.
    """

    def __init__(
        self,
        path: str,
        endpoint: Any | None = None,
        *,
        handler: Any | None = None,
        methods: list[str] | None = None,
        name: str = "",
    ) -> None:
        """Capture route construction arguments.

        Args:
            path: URL path pattern registered by the admin app.
            endpoint: Function-style route handler.
            handler: Controller-style route handler accepted for Lilya parity.
            methods: Optional HTTP methods allowed by the route.
            name: Route name used by admin URL generation.
        """
        self.path = path
        self.endpoint = endpoint or handler
        self.handler = self.endpoint
        self.methods = methods or ["GET"]
        self.name = name


class _FakeDefineMiddleware:
    """Test double for Lilya middleware declarations.

    Lilya stores middleware as declaration objects before wrapping the ASGI app.
    The fake keeps the class and keyword arguments visible for assertions.
    """

    def __init__(self, cls: Any, **kwargs: Any) -> None:
        """Record middleware class and configuration.

        Args:
            cls: ASGI middleware class being declared.
            **kwargs: Keyword arguments that Lilya would pass at runtime.
        """
        self.cls = cls
        self.kwargs = kwargs


class _FakeTemplates:
    """Test double for Lilya's Jinja template wrapper.

    The fake mirrors the ``get_template_response`` method used by Saffier's
    admin app and exposes ``env.globals`` so template globals can be registered.
    """

    def __init__(self, directory: list[str]):
        """Store template search directories.

        Args:
            directory: Template directories supplied by ``AdminConfig``.
        """
        self.directory = directory
        self.env = types.SimpleNamespace(globals={})

    def get_template_response(
        self,
        request: Any,
        template_name: str,
        context: dict[str, Any],
        *,
        status_code: int = 200,
    ) -> _FakeResponse:
        """Return a fake rendered template response.

        Args:
            request: Request object passed by the route handler.
            template_name: Template path requested by the handler.
            context: Template context built by the admin application.
            status_code: HTTP status code for the response.

        Returns:
            _FakeResponse: Captured template response.
        """
        del request
        return _FakeResponse(payload=context, status_code=status_code, template=template_name)


class _FakeRequest:
    """Minimal Lilya request shape consumed by admin handlers.

    The route handlers only read path parameters, query parameters, the HTTP
    method, form data, and ``url_for``. This fake models exactly that surface so
    unit tests can prove Saffier's handler decisions without running a router.
    """

    def __init__(
        self,
        *,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        method: str = "GET",
        form_data: dict[str, Any] | None = None,
    ) -> None:
        """Create a request with path, query, method, and form data.

        Args:
            path_params: Values that Lilya would parse from the route path.
            query_params: Query string values used by list and search routes.
            method: HTTP method visible to form handlers.
            form_data: Form payload returned by ``form()``.
        """
        self.path_params = path_params or {}
        self.query_params = query_params or {}
        self.method = method
        self._form_data = form_data or {}

    async def form(self) -> Any:
        """Return a mapping with Lilya's ``multi_items`` form API.

        Returns:
            Any: Dict-like form object used by ``AdminSite.form_to_payload``.
        """

        class _Form(dict):
            """Small form mapping exposing the multi-item API used by Saffier.

            Lilya form objects expose ``multi_items`` for repeated fields. The
            fake form implements that method so ``AdminSite.form_to_payload``
            sees the same shape it receives at runtime.
            """

            def multi_items(self) -> list[tuple[str, Any]]:
                """Return submitted form items in insertion order.

                Returns:
                    list[tuple[str, Any]]: Form key/value pairs.
                """
                return list(self.items())

        return _Form(self._form_data)

    def url_for(self, route_name: str, **params: Any) -> str:
        """Build a deterministic fake URL for route-helper assertions.

        Args:
            route_name: Name passed to Lilya's URL generator.
            **params: Path parameters for the named route.

        Returns:
            str: Predictable fake URL path.
        """
        extra = "/".join(str(value) for value in params.values())
        return f"/{route_name}/{extra}".rstrip("/")


class _FakeChildLilya:
    """Test double for ``lilya.apps.ChildLilya``.

    The factory result is inspected by unit tests for routes, middleware, and
    debug configuration. The fake stores those values without emulating Lilya's
    ASGI dispatch, which is covered separately by integration tests.
    """

    def __init__(self, *, debug: bool, routes: list[_FakeRoutePath], middleware: list[Any]):
        """Capture the admin app configuration.

        Args:
            debug: Debug flag passed to ``create_admin_app``.
            routes: Lilya route declarations.
            middleware: Lilya middleware declarations.
        """
        self.debug = debug
        self.routes = routes
        self.middleware = middleware


class _FakeSessionContextMiddleware:
    """Placeholder for Lilya's session-context middleware.

    ``create_admin_app`` should always declare the session-context middleware so
    flash messages and recent-model state work at runtime. The fake class gives
    assertions a stable middleware name without wrapping an ASGI app.
    """


def _install_fake_lilya(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install Lilya test doubles into ``sys.modules``.

    The admin module imports Lilya lazily inside ``create_admin_app``. Replacing
    those modules before calling the factory gives unit tests fast route-level
    proof without depending on Lilya's router internals.

    Args:
        monkeypatch: Pytest monkeypatch fixture used to update ``sys.modules``.
    """
    lilya_pkg = types.ModuleType("lilya")
    apps = types.ModuleType("lilya.apps")
    middleware = types.ModuleType("lilya.middleware")
    session_context = types.ModuleType("lilya.middleware.session_context")
    requests = types.ModuleType("lilya.requests")
    responses = types.ModuleType("lilya.responses")
    routing = types.ModuleType("lilya.routing")
    templating = types.ModuleType("lilya.templating")

    apps.ChildLilya = _FakeChildLilya
    middleware.DefineMiddleware = _FakeDefineMiddleware
    session_context.SessionContextMiddleware = _FakeSessionContextMiddleware
    requests.Request = _FakeRequest
    responses.JSONResponse = lambda payload, status_code=200: _FakeResponse(
        payload,
        status_code,
    )
    responses.RedirectResponse = lambda url, status_code=303: _FakeResponse(url, status_code)
    routing.RoutePath = _FakeRoutePath
    templating.Jinja2Template = _FakeTemplates
    responses.HTMLResponse = lambda payload, status_code=200: _FakeResponse(payload, status_code)

    monkeypatch.setitem(sys.modules, "lilya", lilya_pkg)
    monkeypatch.setitem(sys.modules, "lilya.apps", apps)
    monkeypatch.setitem(sys.modules, "lilya.middleware", middleware)
    monkeypatch.setitem(sys.modules, "lilya.middleware.session_context", session_context)
    monkeypatch.setitem(sys.modules, "lilya.requests", requests)
    monkeypatch.setitem(sys.modules, "lilya.responses", responses)
    monkeypatch.setitem(sys.modules, "lilya.routing", routing)
    monkeypatch.setitem(sys.modules, "lilya.templating", templating)


@dataclass
class DummyModel:
    """Small model-like class used by the fake admin site.

    The application route tests need only model metadata, primary-key naming,
    and a display name. A dataclass keeps the fixture small while still exposing
    the attributes that templates and route handlers read from real models.
    """

    __name__ = "User"
    meta = types.SimpleNamespace(no_admin_create=False)
    pkname: str = "id"
    pknames = ("id",)


class DummyInstance:
    """Small persisted-object stand-in used by fake CRUD calls.

    Instances behave like a tiny subset of Saffier models: they expose a primary
    key, public fields, and ``model_dump``. That is enough for route-level tests
    while full persistence is verified in the ASGI integration battery.
    """

    def __init__(self, pk: int, name: str = "alice") -> None:
        """Create a fake instance with Saffier-like public attributes.

        Args:
            pk: Primary-key value.
            name: Display name used by tests and search.
        """
        self.id = pk
        self.name = name
        self.active = False
        self.pkname = "id"

    @property
    def pk(self) -> int:
        """Return the fake primary key.

        Returns:
            int: Primary-key value.
        """
        return self.id

    def model_dump(self) -> dict[str, Any]:
        """Serialize fields the admin templates display.

        Returns:
            dict[str, Any]: Field values keyed by name.
        """
        return {"id": self.id, "name": self.name, "active": self.active}


class DummySite:
    """Fake ``AdminSite`` that exercises the admin route contract.

    The fake implements the same methods ``create_admin_app`` calls on the real
    service: model discovery, schema generation, pagination, CRUD, and payload
    conversion. It keeps state in memory so tests can assert route behavior
    precisely before broader integration tests hit the database.
    """

    def __init__(self, *, no_admin_create: bool = False) -> None:
        """Create an in-memory fake admin site.

        Args:
            no_admin_create: Whether create routes should be disabled for the
                fake model.
        """
        self.config = AdminConfig(title="Admin")
        self.instances = {1: DummyInstance(1)}
        self.no_admin_create = no_admin_create
        DummyModel.meta.no_admin_create = no_admin_create

    def get_registered_models(self) -> dict[str, type[DummyModel]]:
        """Return the fake model registry.

        Returns:
            dict[str, type[DummyModel]]: Single-model registry mapping.
        """
        return {"User": DummyModel}

    async def get_model_counts(self) -> list[dict[str, Any]]:
        """Return dashboard count data for the fake model.

        Returns:
            list[dict[str, Any]]: Count rows matching ``AdminSite`` output.
        """
        return [
            {
                "name": "User",
                "verbose": "User",
                "count": len(self.instances),
                "no_admin_create": self.no_admin_create,
            }
        ]

    def can_create_model(self, model_name: str) -> bool:
        """Return whether the fake model accepts create requests.

        Args:
            model_name: Model name supplied by the route.

        Returns:
            bool: False when ``no_admin_create`` was configured.
        """
        self.get_model(model_name)
        return not self.no_admin_create

    def get_model(self, model_name: str) -> type[DummyModel]:
        """Resolve the fake model or raise an admin lookup error.

        Args:
            model_name: Requested model name.

        Returns:
            type[DummyModel]: Fake model class.
        """
        if model_name != "User":
            raise AdminModelNotFound("missing")
        return DummyModel

    def get_model_fields(
        self,
        model_name: str,
        *,
        for_write: bool = False,
    ) -> list[dict[str, Any]]:
        """Return field descriptors consumed by templates.

        Args:
            model_name: Requested model name.
            for_write: Whether read-only fields should be omitted.

        Returns:
            list[dict[str, Any]]: Fake field descriptors.
        """
        self.get_model(model_name)
        fields = [
            {"name": "id", "required": False, "read_only": True, "primary_key": True},
            {"name": "name", "required": True, "read_only": False, "primary_key": False},
            {"name": "active", "required": False, "read_only": False, "primary_key": False},
        ]
        if for_write:
            return [field for field in fields if field["name"] != "id"]
        return fields

    def get_model_schema(self, model_name: str) -> dict[str, Any]:
        """Return compact fake schema metadata.

        Args:
            model_name: Requested model name.

        Returns:
            dict[str, Any]: Schema metadata used by JSON route tests.
        """
        self.get_model(model_name)
        return {
            "model": model_name,
            "pk_name": "id",
            "can_create": self.can_create_model(model_name),
            "fields": self.get_model_fields(model_name),
        }

    def get_model_editor_schema(self, model_name: str, *, phase: str) -> dict[str, Any]:
        """Return a JSONEditor schema for fake create/edit pages.

        Args:
            model_name: Requested model name.
            phase: Admin editor phase.

        Returns:
            dict[str, Any]: Minimal JSON schema.
        """
        self.get_model(model_name)
        return {
            "title": f"User {phase}",
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

    def create_object_pk(self, instance: DummyInstance) -> str:
        """Encode a fake primary key for route tests.

        Args:
            instance: Fake model instance.

        Returns:
            str: Encoded fake primary key.
        """
        return f"pk-{instance.pk}"

    def parse_object_pk(self, encoded_pk: str) -> dict[str, Any]:
        """Decode fake primary keys.

        Args:
            encoded_pk: Encoded fake primary key.

        Returns:
            dict[str, Any]: Lookup dictionary.
        """
        if not encoded_pk.startswith("pk-"):
            raise AdminValidationError({"pk": "bad"})
        return {"id": int(encoded_pk.removeprefix("pk-"))}

    async def list_objects_with_totals(
        self,
        model_name: str,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        order_by: str | None = None,
    ) -> tuple[Page, int, int]:
        """Return a fake page plus total metadata.

        Args:
            model_name: Requested model name.
            page: Page number.
            page_size: Maximum number of items.
            search: Optional search text.
            order_by: Ignored ordering expression.

        Returns:
            tuple[Page, int, int]: Page object, total records, and total pages.
        """
        del order_by
        self.get_model(model_name)
        items = list(self.instances.values())
        if search:
            items = [item for item in items if search.lower() in item.name.lower()]
        page_obj = Page(
            content=items[:page_size],
            is_first=True,
            is_last=True,
            current_page=page,
            next_page=None,
            previous_page=None,
        )
        return page_obj, len(items), 1

    async def get_object(self, model_name: str, encoded_pk: str) -> DummyInstance:
        """Return a fake instance by encoded primary key.

        Args:
            model_name: Requested model name.
            encoded_pk: Encoded fake primary key.

        Returns:
            DummyInstance: Matching fake instance.
        """
        self.get_model(model_name)
        pk = self.parse_object_pk(encoded_pk)["id"]
        if pk not in self.instances:
            raise ObjectNotFound()
        return self.instances[pk]

    def get_object_display_values(self, instance: DummyInstance) -> dict[str, Any]:
        """Return values for the fake detail template.

        Args:
            instance: Fake instance being displayed.

        Returns:
            dict[str, Any]: Display field mapping.
        """
        return instance.model_dump()

    def get_object_editor_values(self, instance: DummyInstance) -> dict[str, Any]:
        """Return initial values for the fake edit template.

        Args:
            instance: Fake instance being edited.

        Returns:
            dict[str, Any]: JSONEditor start values.
        """
        return instance.model_dump()

    def form_to_payload(self, form_data: Any) -> dict[str, Any]:
        """Convert fake form data into a payload.

        Args:
            form_data: Dict-like submitted form data.

        Returns:
            dict[str, Any]: Payload for fake persistence.
        """
        editor_payload = form_data.get("editor_data")
        if editor_payload:
            return {"name": "json-editor"}
        return dict(form_data)

    async def create_object(self, model_name: str, payload: dict[str, Any]) -> DummyInstance:
        """Persist a fake object.

        Args:
            model_name: Requested model name.
            payload: Submitted payload.

        Returns:
            DummyInstance: Created fake instance.
        """
        self.get_model(model_name)
        if not payload.get("name"):
            raise AdminValidationError({"name": "required"})
        new_pk = max(self.instances) + 1
        instance = DummyInstance(new_pk, payload["name"])
        self.instances[new_pk] = instance
        return instance

    async def update_object(
        self,
        model_name: str,
        encoded_pk: str,
        payload: dict[str, Any],
    ) -> DummyInstance:
        """Update a fake object.

        Args:
            model_name: Requested model name.
            encoded_pk: Encoded fake primary key.
            payload: Submitted payload.

        Returns:
            DummyInstance: Updated fake instance.
        """
        instance = await self.get_object(model_name, encoded_pk)
        if "name" in payload and payload["name"] == "":
            raise AdminValidationError({"name": "required"})
        if "name" in payload:
            instance.name = payload["name"]
        return instance

    async def delete_object(self, model_name: str, encoded_pk: str) -> int:
        """Delete a fake object.

        Args:
            model_name: Requested model name.
            encoded_pk: Encoded fake primary key.

        Returns:
            int: Number of deleted records.
        """
        self.get_model(model_name)
        pk = self.parse_object_pk(encoded_pk)["id"]
        self.instances.pop(pk, None)
        return 1


def _route(app: _FakeChildLilya, route_name: str) -> _FakeRoutePath:
    """Return a route by name from the fake Lilya app.

    Args:
        app: Fake Lilya child app returned by ``create_admin_app``.
        route_name: Route name to locate.

    Returns:
        _FakeRoutePath: Matching fake route declaration.
    """
    for route in app.routes:
        if route.name == route_name:
            return route
    raise AssertionError(f"Route {route_name!r} not found")


@pytest.mark.anyio
async def test_admin_application_routes_and_crud(monkeypatch: pytest.MonkeyPatch):
    """Exercise the admin route handlers through Lilya-shaped fakes.

    This test proves the factory registers all expected routes and that each
    nested handler passes the richer Saffier admin context required by the
    Tailwind/JSONEditor templates.
    """
    _install_fake_lilya(monkeypatch)
    app = create_admin_app(site=DummySite(), debug=True)
    assert isinstance(app, _FakeChildLilya)

    dashboard = await _route(app, "admin_dashboard").endpoint(_FakeRequest())
    assert dashboard.status_code == 200
    assert dashboard.template == "admin/dashboard.html.jinja"
    assert dashboard.payload["total_records"] == 1

    models = await _route(app, "admin_models").endpoint(_FakeRequest(query_params={"q": "user"}))
    assert models.status_code == 200
    assert "User" in models.payload["models"]

    detail = await _route(app, "admin_model_detail").endpoint(
        _FakeRequest(path_params={"name": "User"}, query_params={"q": "ali"})
    )
    assert detail.status_code == 200
    assert detail.payload["total_records"] == 1
    assert detail.payload["can_create"] is True

    schema = await _route(app, "admin_model_schema").endpoint(
        _FakeRequest(path_params={"name": "User"})
    )
    assert schema.status_code == 200
    assert schema.json()["model"] == "User"

    schema_alias = await _route(app, "admin_model_json").endpoint(
        _FakeRequest(path_params={"name": "User"})
    )
    assert schema_alias.status_code == 200
    assert schema_alias.json()["model"] == "User"

    create_get = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="GET")
    )
    assert create_get.status_code == 200
    assert create_get.payload["schema"]

    create_post = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="POST", form_data={"name": "bob"})
    )
    assert create_post.status_code == 303

    object_detail = await _route(app, "admin_model_object").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"})
    )
    assert object_detail.status_code == 200
    assert object_detail.payload["values"]["name"] == "bob"

    edit_get = await _route(app, "admin_model_edit").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"}, method="GET")
    )
    assert edit_get.status_code == 200
    assert edit_get.payload["values_as_json"]

    edit_post = await _route(app, "admin_model_edit").endpoint(
        _FakeRequest(
            path_params={"name": "User", "pk": "pk-2"},
            method="POST",
            form_data={"name": "bobby"},
        )
    )
    assert edit_post.status_code == 303

    delete = await _route(app, "admin_model_delete").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"}, method="POST")
    )
    assert delete.status_code == 303


@pytest.mark.anyio
async def test_admin_application_error_paths_auth_and_no_create(
    monkeypatch: pytest.MonkeyPatch,
):
    """Cover auth middleware, error branches, and disabled create redirects.

    The fake app should install Lilya session middleware before optional basic
    auth, reject unknown models and malformed primary keys, preserve schema
    context on validation errors, and redirect away from create pages when
    ``Meta.no_admin_create`` disables object creation.
    """
    _install_fake_lilya(monkeypatch)
    app = create_admin_app(
        site=DummySite(no_admin_create=True),
        auth_username="admin",
        auth_password="secret",
    )

    assert [item.cls.__name__ for item in app.middleware] == [
        "_FakeSessionContextMiddleware",
        "BasicAuthMiddleware",
    ]
    auth_middleware = app.middleware[-1]
    assert auth_middleware.kwargs == {"username": "admin", "password": "secret"}

    create_get = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="GET")
    )
    assert create_get.status_code == 303
    assert create_get.url == "/admin_model_detail/User"

    bad_model = await _route(app, "admin_model_detail").endpoint(
        _FakeRequest(path_params={"name": "Unknown"})
    )
    assert bad_model.status_code == 404

    bad_pk = await _route(app, "admin_model_object").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "wrong"})
    )
    assert bad_pk.status_code == 404

    app = create_admin_app(site=DummySite())
    bad_create = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="POST", form_data={"name": ""})
    )
    assert bad_create.status_code == 400
    assert bad_create.payload["schema"]

    bad_edit = await _route(app, "admin_model_edit").endpoint(
        _FakeRequest(
            path_params={"name": "User", "pk": "pk-1"},
            method="POST",
            form_data={"name": ""},
        )
    )
    assert bad_edit.status_code == 400
    assert bad_edit.payload["values_as_json"]


@pytest.mark.anyio
async def test_admin_application_uses_public_prefix_for_redirects(
    monkeypatch: pytest.MonkeyPatch,
):
    """Prove admin redirects can use a reverse-proxy public prefix.

    A reverse proxy such as nginx can expose the admin under a public prefix
    that differs from the mounted ASGI route. Redirects must honor
    ``AdminConfig.admin_prefix_url`` rather than deriving public URLs from the
    incoming fake request path.
    """
    _install_fake_lilya(monkeypatch)
    site = DummySite()
    site.config = AdminConfig(admin_prefix_url="/nginx/admin")
    app = create_admin_app(site=site)

    create_post = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="POST", form_data={"name": "bob"})
    )
    assert create_post.status_code == 303
    assert create_post.url == "/nginx/admin/models/User/pk-2"

    delete = await _route(app, "admin_model_delete").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"}, method="POST")
    )
    assert delete.status_code == 303
    assert delete.url == "/nginx/admin/models/User"


@pytest.mark.anyio
async def test_admin_not_found_uses_configured_branding_and_prefix(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify the admin 404 helper is driven by ``AdminConfig``.

    The 404 helper can run outside ``create_admin_app`` as a Lilya exception
    handler, so it must not duplicate default titles, colors, or URL-prefix
    rules. This regression test uses the fake Lilya template layer to inspect
    the context passed to the rendered 404 template.
    """
    _install_fake_lilya(monkeypatch)
    config = AdminConfig(
        admin_prefix_url="/proxy/admin",
        title="Configured Title",
        menu_title="Configured Admin",
        dashboard_title="Configured Dashboard",
        favicon="/favicon.ico",
        sidebar_bg_colour="#123456",
    )

    response = await admin_not_found(_FakeRequest(), config=config)

    assert response.status_code == 404
    assert response.template == "admin/404.html.jinja"
    assert response.payload["title"] == "Configured Title"
    assert response.payload["page_title"] == "Admin page not found"
    assert response.payload["menu_title"] == "Configured Admin"
    assert response.payload["dashboard_title"] == "Configured Dashboard"
    assert response.payload["favicon"] == "/favicon.ico"
    assert response.payload["sidebar_bg_colour"] == "#123456"
    assert response.payload["admin_url"]("admin_models") == "/proxy/admin/models"
