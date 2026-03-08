from __future__ import annotations

from typing import Any

from saffier.exceptions import ObjectNotFound

from .config import AdminConfig
from .exceptions import AdminModelNotFound, AdminValidationError
from .permissions import BasicAuthMiddleware
from .site import AdminSite


def create_admin_app(
    *,
    site: AdminSite | None = None,
    registry: Any | None = None,
    config: AdminConfig | None = None,
    debug: bool = False,
    auth_username: str | None = None,
    auth_password: str | None = None,
) -> Any:
    """
    Creates an ASGI admin application.

    Requires optional dependencies: `starlette` and `jinja2`.
    """
    try:
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.requests import Request
        from starlette.responses import JSONResponse, RedirectResponse
        from starlette.routing import Route
        from starlette.templating import Jinja2Templates
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "starlette and jinja2 are required to run saffier.contrib.admin."
        ) from exc

    if site is None:
        if registry is None:
            raise RuntimeError("Pass either `site` or `registry` to create_admin_app.")
        site = AdminSite(registry=registry, config=config)

    admin_config = config or site.config
    templates = Jinja2Templates(directory=admin_config.template_directories())
    templates.env.globals["getattr"] = getattr

    def with_common(request: Any, **context: Any) -> dict[str, Any]:
        return {
            "request": request,
            "title": admin_config.title,
            "menu_title": admin_config.menu_title,
            "dashboard_title": admin_config.dashboard_title,
            "favicon": admin_config.favicon,
            "sidebar_bg_colour": admin_config.sidebar_bg_colour,
            **context,
        }

    async def dashboard(request: Request) -> Any:
        model_stats = await site.get_model_counts()
        total_records = sum(item["count"] for item in model_stats)
        top_model = max(
            model_stats, key=lambda item: item["count"], default={"name": "N/A", "count": 0}
        )
        return templates.TemplateResponse(
            "admin/dashboard.html.jinja",
            with_common(
                request,
                model_stats=model_stats,
                total_records=total_records,
                top_model=top_model,
            ),
        )

    async def models(request: Request) -> Any:
        query = request.query_params.get("q", "").strip().lower()
        all_models = site.get_registered_models()
        if query:
            all_models = {
                name: model
                for name, model in all_models.items()
                if query in name.lower() or query in model.__name__.lower()
            }
        return templates.TemplateResponse(
            "admin/models.html.jinja",
            with_common(request, models=all_models, query=query),
        )

    async def model_detail(request: Request) -> Any:
        name = request.path_params["name"]
        page = max(int(request.query_params.get("page", "1")), 1)
        per_page = min(max(int(request.query_params.get("per_page", "25")), 1), 250)
        search = request.query_params.get("q", "").strip()

        try:
            model = site.get_model(name)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

        page_obj = await site.list_objects(
            name,
            page=page,
            page_size=per_page,
            search=search,
            order_by=None,
        )
        objects = [{"instance": obj, "pk": site.create_object_pk(obj)} for obj in page_obj.content]
        return templates.TemplateResponse(
            "admin/model_detail.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                model_fields=site.get_model_fields(name),
                objects=objects,
                page=page_obj,
                query=search,
                per_page=per_page,
            ),
        )

    async def model_schema(request: Request) -> Any:
        name = request.path_params["name"]
        try:
            payload = site.get_model_schema(name)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return JSONResponse(payload)

    async def model_object_detail(request: Request) -> Any:
        name = request.path_params["name"]
        encoded_pk = request.path_params["pk"]
        try:
            instance = await site.get_object(name, encoded_pk)
            model = site.get_model(name)
        except (AdminModelNotFound, AdminValidationError, ObjectNotFound) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return templates.TemplateResponse(
            "admin/model_object_detail.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                instance=instance,
                encoded_pk=encoded_pk,
            ),
        )

    async def model_object_create(request: Request) -> Any:
        name = request.path_params["name"]
        try:
            model = site.get_model(name)
            fields = site.get_model_fields(name, for_write=True)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

        if request.method == "POST":
            form = await request.form()
            try:
                payload = site.form_to_payload(form)
                created = await site.create_object(name, payload)
            except AdminValidationError as exc:
                return templates.TemplateResponse(
                    "admin/model_object_create.html.jinja",
                    with_common(
                        request,
                        model_name=name,
                        model=model,
                        model_fields=fields,
                        errors=exc.errors,
                        payload=payload if "payload" in locals() else {},
                    ),
                    status_code=400,
                )

            encoded_pk = site.create_object_pk(created)
            url = request.url_for("admin_model_object", name=name, pk=encoded_pk)
            return RedirectResponse(url=str(url), status_code=303)

        return templates.TemplateResponse(
            "admin/model_object_create.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                model_fields=fields,
                errors={},
                payload={},
            ),
        )

    async def model_object_edit(request: Request) -> Any:
        name = request.path_params["name"]
        encoded_pk = request.path_params["pk"]
        try:
            model = site.get_model(name)
            instance = await site.get_object(name, encoded_pk)
            fields = site.get_model_fields(name, for_write=True)
        except (AdminModelNotFound, AdminValidationError, ObjectNotFound) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

        if request.method == "POST":
            form = await request.form()
            try:
                payload = site.form_to_payload(form)
                instance = await site.update_object(name, encoded_pk, payload)
            except AdminValidationError as exc:
                return templates.TemplateResponse(
                    "admin/model_object_edit.html.jinja",
                    with_common(
                        request,
                        model_name=name,
                        model=model,
                        instance=instance,
                        model_fields=fields,
                        errors=exc.errors,
                        payload=payload if "payload" in locals() else {},
                        encoded_pk=encoded_pk,
                    ),
                    status_code=400,
                )

            url = request.url_for("admin_model_object", name=name, pk=encoded_pk)
            return RedirectResponse(url=str(url), status_code=303)

        return templates.TemplateResponse(
            "admin/model_object_edit.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                instance=instance,
                model_fields=fields,
                errors={},
                payload=instance.model_dump(),
                encoded_pk=encoded_pk,
            ),
        )

    async def model_object_delete(request: Request) -> Any:
        name = request.path_params["name"]
        encoded_pk = request.path_params["pk"]
        try:
            await site.delete_object(name, encoded_pk)
        except (AdminModelNotFound, AdminValidationError, ObjectNotFound) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return RedirectResponse(
            url=str(request.url_for("admin_model_detail", name=name)), status_code=303
        )

    middleware = []
    if auth_password is not None:
        middleware.append(
            Middleware(
                BasicAuthMiddleware,
                username=auth_username or "admin",
                password=auth_password,
            )
        )

    routes = [
        Route("/", dashboard, name="admin_dashboard"),
        Route("/models", models, name="admin_models"),
        Route("/models/{name}", model_detail, name="admin_model_detail"),
        Route("/models/{name}/schema", model_schema, name="admin_model_schema"),
        Route(
            "/models/{name}/create",
            model_object_create,
            methods=["GET", "POST"],
            name="admin_model_create",
        ),
        Route("/models/{name}/{pk}", model_object_detail, name="admin_model_object"),
        Route(
            "/models/{name}/{pk}/edit",
            model_object_edit,
            methods=["GET", "POST"],
            name="admin_model_edit",
        ),
        Route(
            "/models/{name}/{pk}/delete",
            model_object_delete,
            methods=["POST"],
            name="admin_model_delete",
        ),
    ]

    return Starlette(debug=debug, routes=routes, middleware=middleware)
