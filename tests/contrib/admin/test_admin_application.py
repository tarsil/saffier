from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from saffier.contrib.admin.application import create_admin_app
from saffier.contrib.admin.config import AdminConfig
from saffier.contrib.admin.exceptions import AdminModelNotFound, AdminValidationError
from saffier.contrib.pagination.base import Page
from saffier.exceptions import ObjectNotFound


class _FakeResponse:
    def __init__(self, payload: Any = None, status_code: int = 200, template: str | None = None):
        self.payload = payload
        self.status_code = status_code
        self.template = template
        self.url = payload if isinstance(payload, str) else None

    def json(self) -> Any:
        return self.payload


class _FakeRoute:
    def __init__(self, path: str, endpoint: Any, methods: list[str] | None = None, name: str = ""):
        self.path = path
        self.endpoint = endpoint
        self.methods = methods or ["GET"]
        self.name = name


class _FakeMiddleware:
    def __init__(self, cls: Any, **kwargs: Any):
        self.cls = cls
        self.kwargs = kwargs


class _FakeTemplates:
    def __init__(self, directory: list[str]):
        self.directory = directory
        self.env = types.SimpleNamespace(globals={})

    def TemplateResponse(self, template: str, context: dict[str, Any], status_code: int = 200):
        return _FakeResponse(payload=context, status_code=status_code, template=template)


class _FakeRequest:
    def __init__(
        self,
        *,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        method: str = "GET",
        form_data: dict[str, Any] | None = None,
    ) -> None:
        self.path_params = path_params or {}
        self.query_params = query_params or {}
        self.method = method
        self._form_data = form_data or {}

    async def form(self) -> Any:
        class _Form(dict):
            def multi_items(self):
                return list(self.items())

        return _Form(self._form_data)

    def url_for(self, route_name: str, **params: Any) -> str:
        extra = "/".join(str(value) for value in params.values())
        return f"/{route_name}/{extra}".rstrip("/")


class _FakeStarlette:
    def __init__(self, *, debug: bool, routes: list[_FakeRoute], middleware: list[Any]):
        self.debug = debug
        self.routes = routes
        self.middleware = middleware


def _install_fake_starlette(monkeypatch: pytest.MonkeyPatch) -> None:
    starlette_pkg = types.ModuleType("starlette")
    applications = types.ModuleType("starlette.applications")
    middleware = types.ModuleType("starlette.middleware")
    requests = types.ModuleType("starlette.requests")
    responses = types.ModuleType("starlette.responses")
    routing = types.ModuleType("starlette.routing")
    templating = types.ModuleType("starlette.templating")

    applications.Starlette = _FakeStarlette
    middleware.Middleware = _FakeMiddleware
    requests.Request = _FakeRequest
    responses.JSONResponse = lambda payload, status_code=200: _FakeResponse(payload, status_code)
    responses.RedirectResponse = lambda url, status_code=303: _FakeResponse(url, status_code)
    routing.Route = _FakeRoute
    templating.Jinja2Templates = _FakeTemplates

    monkeypatch.setitem(sys.modules, "starlette", starlette_pkg)
    monkeypatch.setitem(sys.modules, "starlette.applications", applications)
    monkeypatch.setitem(sys.modules, "starlette.middleware", middleware)
    monkeypatch.setitem(sys.modules, "starlette.requests", requests)
    monkeypatch.setitem(sys.modules, "starlette.responses", responses)
    monkeypatch.setitem(sys.modules, "starlette.routing", routing)
    monkeypatch.setitem(sys.modules, "starlette.templating", templating)


@dataclass
class DummyModel:
    __name__ = "User"
    pkname: str = "id"


class DummyInstance:
    def __init__(self, pk: int, name: str = "alice") -> None:
        self.id = pk
        self.name = name
        self.active = False
        self.pkname = "id"

    @property
    def pk(self) -> int:
        return self.id

    def model_dump(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "active": self.active}


class DummySite:
    def __init__(self) -> None:
        self.config = AdminConfig(title="Admin")
        self.instances = {1: DummyInstance(1)}

    def get_registered_models(self) -> dict[str, type[DummyModel]]:
        return {"User": DummyModel}

    async def get_model_counts(self) -> list[dict[str, Any]]:
        return [{"name": "User", "verbose": "User", "count": len(self.instances)}]

    def get_model(self, model_name: str) -> type[DummyModel]:
        if model_name != "User":
            raise AdminModelNotFound("missing")
        return DummyModel

    def get_model_fields(
        self, model_name: str, *, for_write: bool = False
    ) -> list[dict[str, Any]]:
        self.get_model(model_name)
        fields = [
            {"name": "id", "required": False, "read_only": True},
            {"name": "name", "required": True, "read_only": False},
            {"name": "active", "required": False, "read_only": False},
        ]
        if for_write:
            return [field for field in fields if field["name"] != "id"]
        return fields

    def get_model_schema(self, model_name: str) -> dict[str, Any]:
        self.get_model(model_name)
        return {"model": model_name, "pk_name": "id", "fields": self.get_model_fields(model_name)}

    def create_object_pk(self, instance: DummyInstance) -> str:
        return f"pk-{instance.pk}"

    def parse_object_pk(self, encoded_pk: str) -> dict[str, Any]:
        if not encoded_pk.startswith("pk-"):
            raise AdminValidationError({"pk": "bad"})
        return {"id": int(encoded_pk.removeprefix("pk-"))}

    async def list_objects(
        self,
        model_name: str,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        order_by: str | None = None,
    ) -> Page:
        self.get_model(model_name)
        items = list(self.instances.values())
        if search:
            items = [item for item in items if search.lower() in item.name.lower()]
        return Page(
            content=items[:page_size],
            is_first=True,
            is_last=True,
            current_page=page,
            next_page=None,
            previous_page=None,
        )

    async def get_object(self, model_name: str, encoded_pk: str) -> DummyInstance:
        self.get_model(model_name)
        pk = self.parse_object_pk(encoded_pk)["id"]
        if pk not in self.instances:
            raise ObjectNotFound()
        return self.instances[pk]

    def form_to_payload(self, form_data: Any) -> dict[str, Any]:
        editor_payload = form_data.get("editor_data")
        if editor_payload:
            return {"name": "json-editor"}
        return dict(form_data)

    async def create_object(self, model_name: str, payload: dict[str, Any]) -> DummyInstance:
        self.get_model(model_name)
        if not payload.get("name"):
            raise AdminValidationError({"name": "required"})
        new_pk = max(self.instances) + 1
        instance = DummyInstance(new_pk, payload["name"])
        self.instances[new_pk] = instance
        return instance

    async def update_object(
        self, model_name: str, encoded_pk: str, payload: dict[str, Any]
    ) -> DummyInstance:
        instance = await self.get_object(model_name, encoded_pk)
        if "name" in payload and payload["name"] == "":
            raise AdminValidationError({"name": "required"})
        if "name" in payload:
            instance.name = payload["name"]
        return instance

    async def delete_object(self, model_name: str, encoded_pk: str) -> int:
        pk = self.parse_object_pk(encoded_pk)["id"]
        self.instances.pop(pk, None)
        return 1


def _route(app: _FakeStarlette, route_name: str) -> _FakeRoute:
    for route in app.routes:
        if route.name == route_name:
            return route
    raise AssertionError(f"Route {route_name!r} not found")


@pytest.mark.anyio
async def test_admin_application_routes_and_crud(monkeypatch: pytest.MonkeyPatch):
    _install_fake_starlette(monkeypatch)
    app = create_admin_app(site=DummySite(), debug=True)
    assert isinstance(app, _FakeStarlette)

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

    schema = await _route(app, "admin_model_schema").endpoint(
        _FakeRequest(path_params={"name": "User"})
    )
    assert schema.status_code == 200
    assert schema.json()["model"] == "User"

    create_get = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="GET")
    )
    assert create_get.status_code == 200

    create_post = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="POST", form_data={"name": "bob"})
    )
    assert create_post.status_code == 303

    object_detail = await _route(app, "admin_model_object").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"})
    )
    assert object_detail.status_code == 200

    edit_get = await _route(app, "admin_model_edit").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "pk-2"}, method="GET")
    )
    assert edit_get.status_code == 200

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
async def test_admin_application_error_paths_and_auth(monkeypatch: pytest.MonkeyPatch):
    _install_fake_starlette(monkeypatch)
    app = create_admin_app(
        site=DummySite(),
        auth_username="admin",
        auth_password="secret",
    )

    assert len(app.middleware) == 1
    middleware = app.middleware[0]
    assert middleware.cls.__name__ == "BasicAuthMiddleware"

    bad_model = await _route(app, "admin_model_detail").endpoint(
        _FakeRequest(path_params={"name": "Unknown"})
    )
    assert bad_model.status_code == 404

    bad_pk = await _route(app, "admin_model_object").endpoint(
        _FakeRequest(path_params={"name": "User", "pk": "wrong"})
    )
    assert bad_pk.status_code == 404

    bad_create = await _route(app, "admin_model_create").endpoint(
        _FakeRequest(path_params={"name": "User"}, method="POST", form_data={"name": ""})
    )
    assert bad_create.status_code == 400

    bad_edit = await _route(app, "admin_model_edit").endpoint(
        _FakeRequest(
            path_params={"name": "User", "pk": "pk-1"},
            method="POST",
            form_data={"name": ""},
        )
    )
    assert bad_edit.status_code == 400
