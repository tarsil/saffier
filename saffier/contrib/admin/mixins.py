from __future__ import annotations

from typing import TYPE_CHECKING

from saffier.core.db.models.mixins.admin import AdminMixin

if TYPE_CHECKING:
    from saffier.contrib.admin.config import AdminConfig


def get_templates(config: AdminConfig | None = None):
    try:
        from starlette.templating import Jinja2Templates
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "starlette and jinja2 are required to run saffier.contrib.admin."
        ) from exc

    from saffier.contrib.admin.config import AdminConfig as RuntimeAdminConfig

    active_config = config or RuntimeAdminConfig()
    templates = Jinja2Templates(directory=active_config.template_directories())
    templates.env.globals["getattr"] = getattr
    return templates


__all__ = ["AdminMixin", "get_templates"]
