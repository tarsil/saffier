from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AdminConfig:
    """Configuration object for the built-in Saffier admin.

    The admin app reads branding, template search paths, public URL prefix, and
    session secret values from this object. Keeping these values together lets
    programmatic mounts, the CLI server, and exception handlers share one source
    of truth instead of hardcoding titles or colors in controllers.
    """

    admin_prefix_url: str | None = None
    admin_extra_templates: list[str | os.PathLike[str]] = field(default_factory=list)
    title: str = "Saffier Admin"
    menu_title: str = "Saffier Admin"
    favicon: str = "https://raw.githubusercontent.com/tarsil/saffier/main/docs/overrides/assets/img/favicon.ico"
    sidebar_bg_colour: str = "#ab47bd"
    dashboard_title: str = "Saffier Admin Dashboard"
    secret_key: str | bytes = field(default_factory=lambda: os.urandom(64))

    def template_directories(self) -> list[str]:
        """Return the template search path for Lilya's Jinja renderer.

        Extra template directories are placed before Saffier's built-in admin
        templates so applications can override a page or partial without
        replacing the entire admin package.

        Returns:
            list[str]: Ordered template directories as strings.
        """
        defaults = [str(Path(__file__).resolve().parent / "templates")]
        extras = [str(path) for path in self.admin_extra_templates]
        return [*extras, *defaults]
