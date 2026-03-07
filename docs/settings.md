# Settings

Saffier uses a Monkay-backed settings layer with a Python-native settings class.

That split is deliberate:

* `BaseSettings` and `SaffierSettings` define values, defaults, and environment casting.
* Monkay handles lazy loading, scoped overrides, preloads, and extension registration.
* Saffier keeps the ORM and model layer free from Pydantic.

## Settings Module

Saffier resolves settings from one environment variable:

* `SAFFIER_SETTINGS_MODULE`

If it is not set, Saffier loads:

`saffier.conf.global_settings.SaffierSettings`

The value must point to a Python class:

```shell
$ export SAFFIER_SETTINGS_MODULE=myproject.configs.settings.Settings
```

## Runtime Resolution

```mermaid
flowchart TD
    A["Process starts"] --> B{"SAFFIER_SETTINGS_MODULE set?"}
    B -- Yes --> C["Load custom settings class"]
    B -- No --> D["Load default SaffierSettings"]
    C --> E["Instantiate settings"]
    D --> E
    E --> F{"evaluate_settings_once_ready() called?"}
    F -- No --> G["Use settings values only"]
    F -- Yes --> H["Import preloads"]
    H --> I["Register settings extensions"]
    I --> J{"Saffier instance already set?"}
    J -- Yes --> K["Apply extensions to instance"]
    J -- No --> L["CLI/app bootstrap continues"]
```

## Building a Custom Settings Class

Subclass `SaffierSettings` and override only what your project needs.

```python title="myproject/configs/settings.py"
from pathlib import Path

from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    migration_directory = Path("db/migrations")
    media_root = Path("var/media")
    media_url = "/media/"
    default_related_lookup_field = "uuid"
    preloads = ("myproject.main",)
```

This keeps the framework defaults while moving project-specific choices into one place.

## BaseSettings

`SaffierSettings` inherits from `saffier.conf.BaseSettings`.

`BaseSettings` provides:

* inherited type-hint discovery across the class MRO
* environment-variable casting based on annotations
* `dict()` and `tuple()` export helpers
* a `post_init()` hook for subclasses that need finalization logic

Example:

```python title="myproject/configs/settings.py"
from pathlib import Path

from saffier.conf import BaseSettings


class AppSettings(BaseSettings):
    debug: bool = False
    worker_count: int = 4
    allowed_hosts: list[str] = []
    media_root: Path = Path("media")
```

With:

```shell
$ export DEBUG=true
$ export WORKER_COUNT=8
$ export ALLOWED_HOSTS=api.example.com,admin.example.com
$ export MEDIA_ROOT=/srv/app/media
```

`AppSettings()` resolves to:

```python
AppSettings(
    debug=True,
    worker_count=8,
    allowed_hosts=["api.example.com", "admin.example.com"],
    media_root=Path("/srv/app/media"),
)
```

## Runtime Helpers

Saffier exposes the settings runtime from `saffier.conf` and re-exports it from `saffier`.

```python
from saffier import (
    configure_settings,
    evaluate_settings_once_ready,
    override_settings,
    reload_settings,
    settings,
    with_settings,
)
```

### `settings`

`settings` is a forwarder to the currently active settings object.

```python
from saffier import settings

assert str(settings.migration_directory) == "migrations"
```

### `reload_settings()`

Reload from `SAFFIER_SETTINGS_MODULE`.

```python
from saffier import reload_settings

reload_settings()
```

Use this in tests or scripts after changing the environment variable.

### `configure_settings()`

Replace the active settings explicitly.

Accepted inputs:

* dotted path string
* settings class
* settings instance

```python
from saffier import configure_settings

configure_settings("myproject.configs.settings.Settings")
configure_settings("myproject.configs.settings.Settings", migration_directory="tmp/migrations")
```

### `with_settings()`

Temporarily replace the active settings inside a scope.

```python
from saffier import settings, with_settings

with with_settings(None, default_related_lookup_field="uuid"):
    assert settings.default_related_lookup_field == "uuid"
```

If the first argument is `None`, Saffier clones the current settings and applies the overrides.

### `override_settings`

`override_settings` is the test-friendly wrapper around `with_settings()`.

It works as:

* a sync context manager
* an async context manager
* a decorator for sync tests
* a decorator for async tests

```python
from saffier import override_settings, settings


@override_settings(default_related_lookup_field="slug")
async def test_related_lookup_override():
    assert settings.default_related_lookup_field == "slug"
```

## Preloads

`preloads` lets Saffier import modules before CLI discovery continues.

This is how you avoid repeating `--app` in projects where your application bootstrap already sets
`saffier.monkay.instance`.

```python title="myproject/configs/settings.py"
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    preloads = ("myproject.main",)
```

Supported preload formats:

* `module.path`
* `module.path:callable`

### What a Preload Should Do

A preload should import code that sets the active Saffier instance.

Preferred pattern:

```python
from saffier import Instance, monkay

monkay.set_instance(Instance(registry=registry, app=app))
```

`Migrate(...)` still does this for compatibility, but it is deprecated.

In practice that usually means a module that creates the app and registers Saffier against it.

```python title="myproject/main.py"
from ravyn import Ravyn

from saffier import Database, Instance, Registry, monkay


database = Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
registry = Registry(database=database)
app = Ravyn()
monkay.set_instance(Instance(registry=registry, app=app))
```

With the preload in settings, these commands can run without `--app`:

```shell
$ saffier shell
$ saffier makemigrations
$ saffier migrate
```

### Discovery Order

For commands that need an application context, Saffier resolves in this order:

1. Explicit `--app`
2. Active Monkay instance created by settings preloads
3. Filesystem auto-discovery (`main.py`, `app.py`, `application.py`, and supported factory functions)

See [Application Discovery](./migrations/discovery.md) for the full CLI behavior.

## Extensions

`extensions` is a list or tuple of Monkay extensions.

These are not arbitrary callables. They must follow the Monkay extension protocol:

* a `name` attribute
* an `apply(self, monkay_instance)` method

```python title="myproject/extensions.py"
class ConfigureMedia:
    name = "configure-media"

    def apply(self, monkay_instance):
        monkay_instance.settings.media_root = "storage/media"
        monkay_instance.settings.media_url = "/media/"
```

```python title="myproject/configs/settings.py"
from myproject.extensions import ConfigureMedia
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    extensions = (ConfigureMedia,)
```

### When Extensions Run

Extensions are registered when `evaluate_settings_once_ready()` is called.

If a Saffier instance already exists because a preload imported an app that already set
`saffier.monkay.instance`,
Saffier applies those extensions immediately to that active instance.

### Dynamic Registration

You can also register extensions in code:

```python
from saffier import add_settings_extension, evaluate_settings_once_ready


class EnableDebugStorage:
    name = "enable-debug-storage"

    def apply(self, monkay_instance):
        monkay_instance.settings.media_root = "tmp/media"


add_settings_extension(EnableDebugStorage)
evaluate_settings_once_ready()
```

Register dynamic extensions before the application is bootstrapped. That keeps extension
application deterministic.

See [Extensions](./extensions.md) for a dedicated guide.

## Migration Settings

The migration system reads these settings directly:

* `migration_directory`
* `alembic_ctx_kwargs`
* `preloads`
* `allow_automigrations`
* `multi_schema`
* `ignore_schema_pattern`
* `migrate_databases`

Example:

```python title="myproject/configs/settings.py"
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    migration_directory = "db/migrations"
    alembic_ctx_kwargs = {
        "compare_type": True,
        "render_as_batch": True,
        "include_schemas": True,
    }
```

This affects:

* `saffier init`
* generated migration `env.py` templates
* runtime Alembic context setup
* `saffier.get_migration_prepared_registry(...)`
* registry-managed automigration flows

`allow_automigrations` gates `Registry(..., automigrate_config=...)` so applications and test
harnesses can opt into "migrate on first connect" without hard-coding that behavior. `multi_schema`,
`ignore_schema_pattern`, and `migrate_databases` keep the generated migration environment aligned
with the active registry metadata layout, including multi-database projects.

## Storage and Upload Settings

The file subsystem reads storage settings from the same class.

Important settings:

* `file_upload_temp_dir`
* `file_upload_permissions`
* `file_upload_directory_permissions`
* `media_root`
* `media_url`
* `storages`

Example:

```python title="myproject/configs/settings.py"
from pathlib import Path

from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    media_root = Path("var/uploads")
    media_url = "/uploads/"
    storages = {
        "default": {
            "backend": "saffier.core.files.storage.filesystem.FileSystemStorage",
            "location": "var/uploads",
            "base_url": "/uploads/",
        }
    }
```

See [Files](./files.md) for storage and upload behavior.

## ORM and Query Settings

Saffier also centralizes ORM-wide behavior in settings.

Important settings:

* `default_related_lookup_field`
* `orm_concurrency_enabled`
* `orm_concurrency_limit`
* `many_to_many_relation`

Typical use cases:

* switching relation lookups to `uuid`
* disabling internal fan-out concurrency in deterministic test environments
* overriding autogenerated many-to-many relation naming patterns

## Shell and Admin Settings

Two parts of the developer experience also come from settings:

* `ipython_args`
* `ptpython_config_file`
* `admin_config`

Example:

```python title="myproject/configs/settings.py"
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    ipython_args = ["--no-banner", "--simple-prompt"]
```

`admin_config` is loaded lazily from the admin contrib when first accessed.

## Default Settings Reference

`SaffierSettings` currently provides these main groups of defaults:

### Runtime and CLI

* `ipython_args`
* `ptpython_config_file`
* `preloads`
* `extensions`
* `migration_directory`
* `alembic_ctx_kwargs`
* `allow_automigrations`
* `multi_schema`
* `ignore_schema_pattern`
* `migrate_databases`

### Files and Storage

* `file_upload_temp_dir`
* `file_upload_permissions`
* `file_upload_directory_permissions`
* `media_root`
* `media_url`
* `storages`

### ORM Behavior

* `use_tz`
* `default_related_lookup_field`
* `orm_concurrency_enabled`
* `orm_concurrency_limit`
* `filter_operators`
* `many_to_many_relation`

### Dialects and Drivers

* `postgres_dialects`
* `mysql_dialects`
* `sqlite_dialects`
* `mssql_dialects`
* `postgres_drivers`
* `mysql_drivers`
* `sqlite_drivers`
* `mssql_drivers`

## Real-World Example

A practical Ravyn project can keep database, migrations, storage, and shell behavior in one place.

```python title="myproject/configs/settings.py"
from pathlib import Path

from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    migration_directory = Path("db/migrations")
    media_root = Path("var/media")
    media_url = "/media/"
    default_related_lookup_field = "uuid"
    ipython_args = ["--no-banner"]
    preloads = ("myproject.main",)
    alembic_ctx_kwargs = {
        "compare_type": True,
        "render_as_batch": True,
    }
```

```python title="myproject/main.py"
from ravyn import Ravyn

from saffier import Database, Instance, Registry, monkay


database = Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
registry = Registry(database=database)
app = Ravyn()
monkay.set_instance(Instance(registry=registry, app=app))
```

Now the project can run:

```shell
$ export SAFFIER_SETTINGS_MODULE=myproject.configs.settings.Settings
$ saffier init
$ saffier makemigrations
$ saffier migrate
$ saffier shell
```

## See Also

* [Extensions](./extensions.md)
* [Application Discovery](./migrations/discovery.md)
* [Migrations](./migrations/migrations.md)
* [Files](./files.md)
