# Admin

Saffier provides a Python-native admin subsystem in `saffier.contrib.admin`:

- `AdminSite` for model discovery, validation, CRUD operations, and pagination.
- `create_admin_app()` for an ASGI admin UI.
- `saffier admin_serve` for local admin serving.

No Pydantic dependency is required.

## Programmatic usage

```python
from saffier.contrib.admin import AdminSite

site = AdminSite(registry=models)
users_page = await site.list_objects("User", page=1, page_size=25)
```

## ASGI app

```python
from saffier.contrib.admin import create_admin_app

admin_app = create_admin_app(registry=models, auth_username="admin", auth_password="secret")
```

## CLI

```bash
saffier --app yourmodule:app admin_serve --admin-path /admin
```

Optional extra dependencies:

```bash
pip install "saffier[admin]"
```
