from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AdminConfig:
    admin_prefix_url: str | None = None
    admin_extra_templates: list[str | os.PathLike[str]] = field(default_factory=list)
    title: str = "Saffier Admin"
    menu_title: str = "Saffier Admin"
    favicon: str = (
        "https://raw.githubusercontent.com/dymmond/saffier/main/docs/overrides/favicon.png"
    )
    sidebar_bg_colour: str = "#1f2937"
    dashboard_title: str = "Saffier Admin Dashboard"
    secret_key: str | bytes = field(default_factory=lambda: os.urandom(64))

    def template_directories(self) -> list[str]:
        defaults = [str(Path(__file__).resolve().parent / "templates")]
        extras = [str(path) for path in self.admin_extra_templates]
        return [*extras, *defaults]
