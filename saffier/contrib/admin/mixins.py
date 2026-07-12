from __future__ import annotations

from typing import TYPE_CHECKING

from saffier.core.db.models.mixins.admin import AdminMixin

if TYPE_CHECKING:
    from saffier.contrib.admin.config import AdminConfig


def get_templates(config: AdminConfig | None = None):
    """Create the Lilya Jinja template engine for the admin UI.

    Saffier admin templates are owned by the Lilya integration layer. Extra
    template directories are loaded before the built-in templates so
    applications can override individual pages without replacing the whole
    admin application.

    Args:
        config: Optional admin configuration. When omitted, a default
            ``AdminConfig`` is created.

    Returns:
        Any: Configured Lilya ``Jinja2Template`` instance.
    """
    try:
        from lilya.templating import Jinja2Template
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("lilya and jinja2 are required to run saffier.contrib.admin.") from exc

    from saffier.contrib.admin.config import AdminConfig as RuntimeAdminConfig

    active_config = config or RuntimeAdminConfig()
    templates = Jinja2Template(directory=active_config.template_directories())
    templates.env.globals["getattr"] = getattr
    return templates


__all__ = ["AdminMixin", "get_templates"]
