from __future__ import annotations

import secrets
from typing import Annotated, Any

from sayer import Option, command

import saffier
from saffier.cli.state import get_migration_app, get_migration_registry
from saffier.contrib.admin import AdminConfig, create_admin_app


@command
def admin_serve(
    port: Annotated[
        int,
        Option(
            8000,
            "-p",
            help="Port to run the admin server.",
            show_default=True,
        ),
    ],
    host: Annotated[
        str,
        Option(
            "localhost",
            help="Server host.",
            show_default=True,
        ),
    ],
    debug: Annotated[
        bool,
        Option(
            False,
            help="Start the app in debug mode.",
            is_flag=True,
        ),
    ],
    create_all: Annotated[
        bool,
        Option(
            False,
            help="Create all models before serving admin.",
            is_flag=True,
        ),
    ],
    log_level: Annotated[
        str,
        Option(
            "info",
            help="Uvicorn log level.",
            show_default=True,
        ),
    ],
    auth_name: Annotated[
        str,
        Option(
            "admin",
            help="Basic auth username.",
            show_default=True,
        ),
    ],
    auth_pw: Annotated[
        str | None,
        Option(
            None,
            help="Basic auth password. Auto-generated when omitted.",
            show_default=False,
        ),
    ],
    admin_path: Annotated[
        str,
        Option(
            "/admin",
            help="Path where the admin app is mounted.",
            show_default=True,
        ),
    ],
) -> None:
    """Run the built-in Saffier admin application.

    The command wraps the discovered app with the admin interface when possible,
    configures basic auth, and can optionally create all tables before serving.
    """
    try:
        import palfrey
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Palfrey is required to run `saffier admin_serve`.") from exc

    app = get_migration_app()
    registry = get_migration_registry()
    if auth_pw is None:
        auth_pw = secrets.token_urlsafe(24)
        print(f"Saffier admin password: {auth_pw}")

    admin_app = create_admin_app(
        registry=registry,
        config=AdminConfig(admin_prefix_url=admin_path),
        debug=debug,
        auth_username=auth_name,
        auth_password=auth_pw,
    )

    try:
        from starlette.applications import Starlette
        from starlette.routing import Mount
    except ImportError:
        final_app: Any = admin_app
    else:
        routes = [Mount(admin_path, app=admin_app)]
        if app is not None:
            routes.append(Mount("/", app=app))
        final_app = Starlette(debug=debug, routes=routes)

    if create_all:
        saffier.run_sync(registry.create_all())

    palfrey.run(
        config_or_app=final_app,
        host=host,
        port=port,
        reload=False,
        lifespan="on",
        log_level=log_level,
    )
