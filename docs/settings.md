# Settings

Saffier settings are loaded lazily from `SAFFIER_SETTINGS_MODULE`.

If the variable is not set, Saffier uses:

`saffier.conf.global_settings.SaffierSettings`

## Custom settings class

Create a class inheriting from `SaffierSettings`:

```python
from dataclasses import dataclass

from saffier.conf.global_settings import SaffierSettings


@dataclass
class MySettings(SaffierSettings):
    ptpython_config_file: str = "~/.config/ptpython/custom.py"
```

Then point the environment variable to it:

```bash
SAFFIER_SETTINGS_MODULE=myproject.configs.settings.MySettings
```

## Runtime settings helpers

Saffier exposes helpers to configure and override settings at runtime:

```python
from saffier.conf import configure_settings, override_settings, reload_settings, settings

# Configure from class path
configure_settings("myproject.configs.settings.MySettings")

# Reload from SAFFIER_SETTINGS_MODULE
reload_settings()

# Temporary override
with override_settings(default_related_lookup_field="uuid"):
    assert settings.default_related_lookup_field == "uuid"
```

## Core options

- `ipython_args`: arguments passed to `saffier shell` with IPython.
- `ptpython_config_file`: config path for `saffier shell --kernel ptpython`.
- `default_related_lookup_field`: default related lookup key (default: `id`).
- `orm_concurrency_enabled`: enables/disables internal concurrent execution helpers.
- `orm_concurrency_limit`: default batch size limit for `run_concurrently` utilities (`None` means unrestricted gather).
- `filter_operators`: mapping of lookup suffixes to SQLAlchemy operators.
- `many_to_many_relation`: attribute name format for generated M2M relation accessors.
- `postgres_dialects`, `mysql_dialects`, `sqlite_dialects`, `mssql_dialects`: supported dialect aliases.
- `postgres_drivers`, `mysql_drivers`, `sqlite_drivers`, `mssql_drivers`: supported async drivers.
