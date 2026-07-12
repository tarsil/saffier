from __future__ import annotations

from typing import TYPE_CHECKING

import saffier

if TYPE_CHECKING:
    from saffier.conf.global_settings import SaffierSettings
    from saffier.core.connection.registry import Registry


class SaffierMiddleware:
    """Bind Saffier registry and settings state around Lilya requests.

    Requests can enter the registry's async context manager and install a
    Monkay ``Instance`` so model/query code resolves the active registry during
    Lilya dispatch. The middleware is intentionally small: Lilya owns the ASGI
    route stack, Saffier owns registry and settings context, and SQLAlchemy
    remains the only database runtime.
    """

    def __init__(
        self,
        app,
        registry: Registry | None = None,
        settings: SaffierSettings | None = None,
        wrap_asgi_app: bool = True,
    ) -> None:
        """Configure request-time registry and settings binding.

        Args:
            app: Downstream ASGI application.
            registry: Optional Saffier registry that should be active while the
                request is handled.
            settings: Optional settings object to expose through Monkay for the
                request.
            wrap_asgi_app: Whether to enter the registry's async connection
                context. Set this to ``False`` when an outer layer already owns
                registry lifecycle but request-local Monkay state is still
                desired.
        """
        self.app = app
        self.registry = registry if registry is not None and wrap_asgi_app else None
        self.overwrite: dict[str, object] = {}

        if registry is not None:
            self.overwrite["instance"] = saffier.Instance(registry=registry, app=self.app)
        if settings is not None:
            self.overwrite["settings"] = settings

    async def __call__(self, scope, receive, send) -> None:
        """Handle one ASGI request with Saffier runtime context installed.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if self.registry is None:
            await self._call_with_overwrite(scope, receive, send)
            return

        async with self.registry:
            await self._call_with_overwrite(scope, receive, send)

    async def _call_with_overwrite(self, scope, receive, send) -> None:
        """Dispatch downstream with optional Monkay overrides.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if not self.overwrite:
            await self.app(scope, receive, send)
            return

        with saffier.monkay.with_full_overwrite(**self.overwrite):
            await self.app(scope, receive, send)


__all__ = ["SaffierMiddleware"]
