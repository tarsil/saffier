# Admin

Saffier provides a Lilya-native admin subsystem in `saffier.contrib.admin`.

The admin has two layers:

- `AdminSite` is the Python service for model discovery, validation, schemas, CRUD, search, and pagination.
- `create_admin_app()` returns a Lilya `ChildLilya` app with the built-in HTML admin interface.
- `saffier admin_serve` runs the admin locally with Lilya session middleware and optional basic auth.

No Pydantic dependency is required.

## Install

```shell
pip install "saffier[admin]"
```

The admin extra installs Lilya, Jinja2, session signing support, multipart form parsing, and a server runtime. The HTML interface loads Tailwind CSS, Font Awesome, and JSONEditor from CDNs.

## Programmatic Usage

```python
from saffier.contrib.admin import AdminSite

site = AdminSite(registry=models)
users_page = await site.list_objects("User", page=1, page_size=25)
```

`AdminSite` is useful when you want admin behavior without serving HTML. It exposes the same model visibility, payload validation, primary-key encoding, and create/update/delete behavior used by the Lilya app.

## Lilya App

```python
from lilya.apps import Lilya
from lilya.middleware import DefineMiddleware
from lilya.middleware.sessions import SessionMiddleware
from lilya.routing import Include

from saffier.contrib.admin import AdminConfig, create_admin_app

config = AdminConfig(admin_prefix_url="/admin")
admin_app = create_admin_app(
    registry=models,
    config=config,
    auth_username="admin",
    auth_password="secret",
)

app = Lilya(
    routes=[
        Include(
            "/admin",
            app=admin_app,
            middleware=[
                DefineMiddleware(
                    SessionMiddleware,
                    secret_key=config.secret_key,
                    session_cookie="admin_session",
                )
            ],
        )
    ]
)
```

`create_admin_app()` installs Saffier's Lilya registry middleware and Lilya session-context middleware. The parent mount must provide Lilya `SessionMiddleware`; `saffier admin_serve` does this automatically.

## Basic Auth Permissions

`create_admin_app(auth_password=...)` protects the mounted admin with `BasicAuthMiddleware`.
Applications that build custom Lilya permission stacks can use the same credential behavior through
`BasicAuthAccess`.

```python
from saffier.contrib.admin.permissions import BasicAuthAccess

protected_admin = BasicAuthAccess(
    admin_app,
    username="admin",
    password="secret",
)
```

`BasicAuthAccess` raises Lilya's `PermissionDenied` with a browser-compatible Basic-auth
challenge. `BasicAuthMiddleware` emits the challenge response directly from the ASGI middleware
stack. Both use constant-time credential comparison.

## Reverse Proxy

Use `AdminConfig.admin_prefix_url` when a proxy exposes the admin at a different public path from the internal ASGI mount.

```python
config = AdminConfig(admin_prefix_url="/proxy/saffier/admin")
admin_app = create_admin_app(registry=models, config=config)
```

With that configuration, links and redirects use `/proxy/saffier/admin/...` even if Lilya receives the request on an internal path such as `/internal-admin`.

The CLI exposes the same setting:

```shell
saffier --app yourmodule admin_serve \
  --admin-path /internal-admin \
  --admin-prefix-url /proxy/saffier/admin
```

## CLI

```shell
saffier --app yourmodule admin_serve --admin-path /admin
```

Useful options:

- `--host` and `--port` choose the listening address.
- `--create-all` creates registered tables before serving.
- `--auth-name` and `--auth-pw` configure HTTP Basic auth.
- `--admin-prefix-url` sets the public URL prefix for links and redirects.

When `--auth-pw` is omitted, the command prints a generated password.

## Model Visibility

Models are visible in admin by default. Set `Meta.in_admin = False` to hide a model.

```python
class AuditLog(saffier.Model):
    message = saffier.TextField()

    class Meta:
        registry = models
        in_admin = False
```

Set `Meta.no_admin_create = True` when a model should be browsable but not directly created from the admin UI.

```python
class ContentType(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        no_admin_create = True
```

The create button is hidden, create routes redirect back to the model list, and direct service calls through `AdminSite.create_object()` are rejected.

## Templates

`AdminConfig.admin_extra_templates` lets applications override admin templates.

```python
config = AdminConfig(
    admin_extra_templates=["templates/admin-overrides"],
)
```

Extra template directories are searched before Saffier's built-in templates, so you can override one page without copying the full admin.
