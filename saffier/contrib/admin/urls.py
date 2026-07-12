from __future__ import annotations

from typing import Any
from urllib.parse import quote

ADMIN_ROUTE_PATHS = {
    "admin_dashboard": "/",
    "admin_models": "/models",
    "admin_model_detail": "/models/{name}",
    "admin_model_schema": "/models/{name}/schema",
    "admin_model_json": "/models/{name}/json",
    "admin_model_create": "/models/{name}/create",
    "admin_model_object": "/models/{name}/{pk}",
    "admin_model_edit": "/models/{name}/{pk}/edit",
    "admin_model_delete": "/models/{name}/{pk}/delete",
}


def normalize_admin_prefix(prefix: str | None) -> str | None:
    """Normalize an externally visible admin URL prefix.

    Saffier admin can be mounted behind a reverse proxy where the browser-facing
    URL differs from the internal ASGI mount path. Normalizing the configured
    prefix once gives templates, redirects, and exception handlers the same
    public URL behavior.

    Args:
        prefix: Optional prefix supplied by ``AdminConfig.admin_prefix_url``.

    Returns:
        str | None: ``None`` when no external prefix is configured, otherwise a
        slash-prefixed value without a trailing slash. The root prefix is
        represented as an empty string so route paths can be appended directly.
    """
    if prefix is None:
        return None
    normalized = prefix.strip()
    if not normalized or normalized == "/":
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def build_admin_path(route_name: str, **params: Any) -> str:
    """Build an admin-relative path for a known route name.

    This helper intentionally covers only Saffier's built-in admin route names.
    It is used when ``admin_prefix_url`` is configured and route generation must
    be independent from the path used to mount the ASGI app.

    Args:
        route_name: Built-in Saffier admin route name.
        **params: Path parameters required by the route.

    Returns:
        str: Admin-relative path beginning with ``/``.

    Raises:
        KeyError: If an unknown route name is requested.
    """
    path = ADMIN_ROUTE_PATHS[route_name]
    for key, value in params.items():
        path = path.replace(f"{{{key}}}", quote(str(value), safe=""))
    return path


def admin_url_for(
    request: Any,
    route_name: str,
    admin_prefix_url: str | None,
    **params: Any,
) -> str:
    """Return a URL for an admin route using Saffier prefix rules.

    Without an explicit ``admin_prefix_url``, Lilya's normal ``request.url_for``
    owns URL generation and can include the actual mount path. When a prefix is
    configured, Saffier follows reverse-proxy-safe behavior and builds URLs from
    that public prefix instead.

    Args:
        request: Lilya request object for the current admin request.
        route_name: Built-in admin route name.
        admin_prefix_url: Optional externally visible admin prefix.
        **params: Path parameters required by the route.

    Returns:
        str: URL path suitable for templates and redirects.
    """
    prefix = normalize_admin_prefix(admin_prefix_url)
    if prefix is None:
        return str(request.url_for(route_name, **params))
    return f"{prefix}{build_admin_path(route_name, **params)}"


__all__ = ["admin_url_for", "build_admin_path", "normalize_admin_prefix"]
