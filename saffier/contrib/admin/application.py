from __future__ import annotations

from typing import Any

import orjson

from saffier.exceptions import ObjectNotFound

from .config import AdminConfig
from .exceptions import AdminModelNotFound, AdminValidationError
from .permissions import BasicAuthMiddleware
from .site import AdminSite
from .urls import admin_url_for, normalize_admin_prefix
from .utils.messages import add_message, get_messages
from .utils.models import add_to_recent_models, get_recent_models


def create_admin_app(
    *,
    session_sub_path: str = "",
    site: AdminSite | None = None,
    registry: Any | None = None,
    config: AdminConfig | None = None,
    settings: Any | None = None,
    debug: bool = False,
    auth_username: str | None = None,
    auth_password: str | None = None,
) -> Any:
    """Create a Lilya admin application for Saffier models.

    The returned application is a ``ChildLilya`` instance. It uses Saffier's
    registry-backed ``AdminSite`` service for all ORM work, Lilya routing and
    responses for the ASGI surface, and optional HTTP Basic auth for the
    stand-alone admin server.

    Args:
        session_sub_path: Optional Lilya session-context sub path used when an
            application hosts more than one admin surface.
        site: Preconfigured admin service. When omitted, ``registry`` is used to
            construct one.
        registry: Saffier registry exposed by the admin and optionally bound to
            the request context through Saffier's Lilya middleware.
        config: Admin configuration controlling branding, template directories,
            and public URL prefix.
        settings: Optional Saffier settings override for the request context.
        debug: Whether the Lilya child app should run in debug mode.
        auth_username: Username for optional HTTP Basic auth.
        auth_password: Password for optional HTTP Basic auth. When omitted, no
            auth middleware is installed.

    Returns:
        Any: Lilya ``ChildLilya`` application ready to mount or serve.
    """
    try:
        from lilya.apps import ChildLilya
        from lilya.middleware import DefineMiddleware
        from lilya.middleware.session_context import SessionContextMiddleware
        from lilya.requests import Request
        from lilya.responses import JSONResponse, RedirectResponse
        from lilya.routing import RoutePath
        from lilya.templating import Jinja2Template
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("lilya and jinja2 are required to run saffier.contrib.admin.") from exc

    from saffier.contrib.lilya.middleware import SaffierMiddleware

    if site is None:
        if registry is None:
            raise RuntimeError("Pass either `site` or `registry` to create_admin_app.")
        site = AdminSite(registry=registry, config=config)

    admin_config = config or site.config
    templates = Jinja2Template(directory=admin_config.template_directories())
    templates.env.globals["getattr"] = getattr

    def with_common(request: Any, **context: Any) -> dict[str, Any]:
        """Build the template context shared by every admin page.

        The base template needs routing helpers, branding, flash messages, and a
        primary-key encoder regardless of which route is being rendered. Keeping
        those values in one helper prevents templates from reaching into Lilya or
        ``AdminSite`` internals directly.

        Args:
            request: Current Lilya request object.
            **context: Route-specific context values.

        Returns:
            dict[str, Any]: Complete template context for Lilya rendering.
        """
        return {
            "request": request,
            "admin_url": lambda route_name, **params: admin_url_for(
                request,
                route_name,
                admin_config.admin_prefix_url,
                **params,
            ),
            "create_object_pk": site.create_object_pk,
            "messages": get_messages(),
            "user": None,
            "url_prefix": normalize_admin_prefix(admin_config.admin_prefix_url) or "",
            "title": admin_config.title,
            "menu_title": admin_config.menu_title,
            "dashboard_title": admin_config.dashboard_title,
            "favicon": admin_config.favicon,
            "sidebar_bg_colour": admin_config.sidebar_bg_colour,
            **context,
        }

    def render_template(
        request: Any,
        template_name: str,
        context: dict[str, Any],
        *,
        status_code: int = 200,
    ) -> Any:
        """Render an admin template through Lilya's Jinja integration.

        The small wrapper keeps handler code independent from the exact Lilya
        templating call signature and gives unit tests one place to replace when
        they fake the template engine.

        Args:
            request: Current Lilya request.
            template_name: Template path inside the admin template loader.
            context: Template context already populated with common admin data.
            status_code: HTTP response status code.

        Returns:
            Any: Lilya template response.
        """
        return templates.get_template_response(
            request,
            template_name,
            context,
            status_code=status_code,
        )

    async def dashboard(request: Request) -> Any:
        """Render the admin dashboard with model counts and recent models.

        Args:
            request: Lilya request for the dashboard route.

        Returns:
            Any: Lilya template response for the dashboard page.
        """
        model_stats = await site.get_model_counts()
        total_records = sum(item["count"] for item in model_stats)
        top_model = max(
            model_stats, key=lambda item: item["count"], default={"name": "N/A", "count": 0}
        )
        return render_template(
            request,
            "admin/dashboard.html.jinja",
            with_common(
                request,
                models=model_stats,
                model_stats=model_stats,
                total_records=total_records,
                top_model=top_model,
                recent_models=get_recent_models(),
            ),
        )

    async def models(request: Request) -> Any:
        """Render the searchable model index.

        Args:
            request: Lilya request carrying an optional ``q`` query parameter.

        Returns:
            Any: Lilya template response containing admin-visible models.
        """
        query = request.query_params.get("q", "").strip().lower()
        all_models = site.get_registered_models()
        if query:
            all_models = {
                name: model
                for name, model in all_models.items()
                if query in name.lower() or query in model.__name__.lower()
            }
        return render_template(
            request,
            "admin/models.html.jinja",
            with_common(request, models=all_models, query=query),
        )

    async def model_detail(request: Request) -> Any:
        """Render a paginated table for one admin-visible model.

        Args:
            request: Lilya request containing the model name path parameter and
                optional pagination/search query parameters.

        Returns:
            Any: Lilya template response for the model list, or JSON ``404``
            when the model is not available in admin.
        """
        name = request.path_params["name"]
        page = max(int(request.query_params.get("page", "1")), 1)
        per_page = min(max(int(request.query_params.get("per_page", "25")), 1), 250)
        search = request.query_params.get("q", "").strip()

        try:
            model = site.get_model(name)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        add_to_recent_models(model)

        page_obj, total_records, total_pages = await site.list_objects_with_totals(
            name,
            page=page,
            page_size=per_page,
            search=search,
            order_by=None,
        )
        objects = [{"instance": obj, "pk": site.create_object_pk(obj)} for obj in page_obj.content]
        return render_template(
            request,
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
                total_records=total_records,
                total_pages=total_pages,
                can_create=site.can_create_model(name),
            ),
        )

    async def model_schema(request: Request) -> Any:
        """Return compact JSON metadata for one admin model.

        Args:
            request: Lilya request containing the model name path parameter.

        Returns:
            Any: JSON response with schema metadata, or JSON ``404`` for an
            unknown model.
        """
        name = request.path_params["name"]
        try:
            payload = site.get_model_schema(name)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return JSONResponse(payload)

    async def model_object_detail(request: Request) -> Any:
        """Render the detail page for one model instance.

        Args:
            request: Lilya request containing model name and encoded primary-key
                path parameters.

        Returns:
            Any: Lilya template response for the object detail page, or JSON
            ``404`` when the model or object cannot be resolved.
        """
        name = request.path_params["name"]
        encoded_pk = request.path_params["pk"]
        try:
            instance = await site.get_object(name, encoded_pk)
            model = site.get_model(name)
        except (AdminModelNotFound, AdminValidationError, ObjectNotFound) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        add_to_recent_models(model)
        return render_template(
            request,
            "admin/model_object_detail.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                instance=instance,
                encoded_pk=encoded_pk,
                object_pk=encoded_pk,
                values=site.get_object_display_values(instance),
                model_fields=site.get_model_fields(name),
                title=f"{model.__name__} object",
            ),
        )

    async def model_object_create(request: Request) -> Any:
        """Render or process the JSONEditor-backed create form.

        Args:
            request: Lilya request containing the model name path parameter and,
                for ``POST`` requests, submitted form data.

        Returns:
            Any: Create form template, validation-error template, or redirect to
            the created object when persistence succeeds.
        """
        name = request.path_params["name"]
        try:
            model = site.get_model(name)
            fields = site.get_model_fields(name, for_write=True)
        except AdminModelNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

        if not site.can_create_model(name):
            add_message("warning", f"Creation is disabled for {name}.")
            url = admin_url_for(
                request,
                "admin_model_detail",
                admin_config.admin_prefix_url,
                name=name,
            )
            return RedirectResponse(url=url, status_code=303)

        if request.method == "POST":
            form = await request.form()
            try:
                payload = site.form_to_payload(form)
                created = await site.create_object(name, payload)
            except AdminValidationError as exc:
                return render_template(
                    request,
                    "admin/model_object_create.html.jinja",
                    with_common(
                        request,
                        model_name=name,
                        model=model,
                        model_fields=fields,
                        schema=orjson.dumps(
                            site.get_model_editor_schema(name, phase="create"),
                            default=str,
                        ).decode(),
                        errors=exc.errors,
                        payload=payload if "payload" in locals() else {},
                    ),
                    status_code=400,
                )

            encoded_pk = site.create_object_pk(created)
            add_message("success", f"{name} was created successfully.")
            url = admin_url_for(
                request,
                "admin_model_object",
                admin_config.admin_prefix_url,
                name=name,
                pk=encoded_pk,
            )
            return RedirectResponse(url=url, status_code=303)

        return render_template(
            request,
            "admin/model_object_create.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                model_fields=fields,
                schema=orjson.dumps(
                    site.get_model_editor_schema(name, phase="create"),
                    default=str,
                ).decode(),
                errors={},
                payload={},
            ),
        )

    async def model_object_edit(request: Request) -> Any:
        """Render or process the JSONEditor-backed edit form.

        Args:
            request: Lilya request containing model name and encoded primary-key
                path parameters plus optional submitted form data.

        Returns:
            Any: Edit form template, validation-error template, or redirect to
            the updated object when persistence succeeds.
        """
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
                return render_template(
                    request,
                    "admin/model_object_edit.html.jinja",
                    with_common(
                        request,
                        model_name=name,
                        model=model,
                        instance=instance,
                        model_fields=fields,
                        schema=orjson.dumps(
                            site.get_model_editor_schema(name, phase="update"),
                            default=str,
                        ).decode(),
                        values_as_json=orjson.dumps(
                            payload
                            if "payload" in locals()
                            else site.get_object_editor_values(instance),
                            default=str,
                        ).decode(),
                        errors=exc.errors,
                        payload=payload if "payload" in locals() else {},
                        encoded_pk=encoded_pk,
                        object=instance,
                    ),
                    status_code=400,
                )

            url = admin_url_for(
                request,
                "admin_model_object",
                admin_config.admin_prefix_url,
                name=name,
                pk=encoded_pk,
            )
            add_message("success", f"{name} was updated successfully.")
            return RedirectResponse(url=url, status_code=303)

        return render_template(
            request,
            "admin/model_object_edit.html.jinja",
            with_common(
                request,
                model_name=name,
                model=model,
                instance=instance,
                model_fields=fields,
                schema=orjson.dumps(
                    site.get_model_editor_schema(name, phase="update"),
                    default=str,
                ).decode(),
                values_as_json=orjson.dumps(
                    site.get_object_editor_values(instance),
                    default=str,
                ).decode(),
                errors={},
                payload=instance.model_dump(),
                encoded_pk=encoded_pk,
                object=instance,
            ),
        )

    async def model_object_delete(request: Request) -> Any:
        """Delete one model instance and redirect back to the model table.

        Args:
            request: Lilya request containing model name and encoded primary-key
                path parameters.

        Returns:
            Any: Redirect response after deletion, or JSON ``404`` when the
            target object cannot be resolved.
        """
        name = request.path_params["name"]
        encoded_pk = request.path_params["pk"]
        try:
            await site.delete_object(name, encoded_pk)
        except (AdminModelNotFound, AdminValidationError, ObjectNotFound) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        add_message("success", f"{name} was deleted successfully.")
        url = admin_url_for(
            request,
            "admin_model_detail",
            admin_config.admin_prefix_url,
            name=name,
        )
        return RedirectResponse(url=url, status_code=303)

    middleware = []
    if registry is not None or settings is not None:
        middleware.append(
            DefineMiddleware(SaffierMiddleware, registry=registry, settings=settings)
        )
    middleware.append(DefineMiddleware(SessionContextMiddleware, sub_path=session_sub_path))
    if auth_password is not None:
        middleware.append(
            DefineMiddleware(
                BasicAuthMiddleware,
                username=auth_username or "admin",
                password=auth_password,
            )
        )

    routes = [
        RoutePath("/", dashboard, name="admin_dashboard"),
        RoutePath("/models", models, name="admin_models"),
        RoutePath("/models/{name}", model_detail, name="admin_model_detail"),
        RoutePath("/models/{name}/schema", model_schema, name="admin_model_schema"),
        RoutePath("/models/{name}/json", model_schema, name="admin_model_json"),
        RoutePath(
            "/models/{name}/create",
            model_object_create,
            methods=["GET", "POST"],
            name="admin_model_create",
        ),
        RoutePath("/models/{name}/{pk}", model_object_detail, name="admin_model_object"),
        RoutePath(
            "/models/{name}/{pk}/edit",
            model_object_edit,
            methods=["GET", "POST"],
            name="admin_model_edit",
        ),
        RoutePath(
            "/models/{name}/{pk}/delete",
            model_object_delete,
            methods=["POST"],
            name="admin_model_delete",
        ),
    ]

    return ChildLilya(debug=debug, routes=routes, middleware=middleware)
