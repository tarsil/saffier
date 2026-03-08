from __future__ import annotations

from typing import TYPE_CHECKING

import saffier

if TYPE_CHECKING:
    from saffier.conf.global_settings import SaffierSettings
    from saffier.core.connection.registry import Registry


class EdgyMiddleware:
    def __init__(
        self,
        app,
        registry: Registry | None = None,
        settings: SaffierSettings | None = None,
        wrap_asgi_app: bool = True,
    ) -> None:
        self.app = app
        self.overwrite: dict[str, object] = {}

        if registry is not None:
            if wrap_asgi_app:
                self.app = registry.asgi(self.app)
            self.overwrite["instance"] = saffier.Instance(registry=registry, app=self.app)
        if settings is not None:
            self.overwrite["settings"] = settings

    async def __call__(self, scope, receive, send) -> None:
        if not self.overwrite:
            await self.app(scope, receive, send)
            return

        with saffier.monkay.with_full_overwrite(**self.overwrite):
            await self.app(scope, receive, send)


__all__ = ["EdgyMiddleware"]
