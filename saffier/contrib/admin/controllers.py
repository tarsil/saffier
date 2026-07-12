from __future__ import annotations

from typing import Any

from saffier.conf import settings
from saffier.contrib.admin.config import AdminConfig
from saffier.contrib.admin.mixins import AdminMixin, get_templates
from saffier.contrib.admin.urls import admin_url_for, normalize_admin_prefix


def _resolve_admin_config(config: AdminConfig | None = None) -> AdminConfig:
    """Resolve the admin configuration used by controller helpers.

    ``admin_not_found`` can be used as a plain Lilya exception handler, where
    Lilya supplies only the request and exception. In that case Saffier should
    still honor the configured admin branding and public URL prefix from
    ``settings.admin_config``. A caller-provided config wins for tests and custom
    integrations.

    Args:
        config: Optional explicit admin configuration.

    Returns:
        AdminConfig: Configuration object used for templates and URL helpers.
    """
    if config is not None:
        return config
    try:
        resolved = settings.admin_config
    except Exception:  # pragma: no cover
        return AdminConfig()
    return resolved if isinstance(resolved, AdminConfig) else AdminConfig()


async def admin_not_found(
    request: Any,
    exc: Exception | None = None,
    config: AdminConfig | None = None,
) -> Any:
    """Render the admin 404 page through Lilya-compatible responses.

    The helper is exported for applications that mount Saffier admin inside a
    larger Lilya application and want the admin-specific not-found page for
    missing admin routes. It uses Saffier's own template configuration and
    Lilya response layer so branding and public-prefix behavior remain
    centralized.

    Args:
        request: Current ASGI request object.
        exc: Optional exception supplied by Lilya's exception handler interface.
        config: Optional admin configuration. When omitted, the helper uses
            ``settings.admin_config`` so branding, templates, and public prefix
            behavior remain centralized.

    Returns:
        Any: Lilya template response when templating is installed, otherwise a
        simple HTML response.
    """
    del exc
    try:
        from lilya.responses import HTMLResponse
    except ImportError:  # pragma: no cover
        return {"detail": "Not found"}

    try:
        active_config = _resolve_admin_config(config)
        templates = get_templates(active_config)
        return templates.get_template_response(
            request,
            "admin/404.html.jinja",
            {
                "request": request,
                "title": active_config.title,
                "page_title": "Admin page not found",
                "menu_title": active_config.menu_title,
                "dashboard_title": active_config.dashboard_title,
                "favicon": active_config.favicon,
                "sidebar_bg_colour": active_config.sidebar_bg_colour,
                "url_prefix": normalize_admin_prefix(active_config.admin_prefix_url) or "",
                "admin_url": lambda route_name, **params: admin_url_for(
                    request,
                    route_name,
                    active_config.admin_prefix_url,
                    **params,
                ),
            },
            status_code=404,
        )
    except Exception:
        return HTMLResponse("Admin page not found.", status_code=404)


__all__ = ["AdminMixin", "admin_not_found", "get_templates"]
