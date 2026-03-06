# Auto Reflection

`saffier.contrib.autoreflection.AutoReflectModel` lets you declare reflection patterns and
materialize reflected models from existing database tables.

## Basic usage

```python
import saffier
from saffier.contrib.autoreflection import AutoReflectModel

database = saffier.Database("postgresql+asyncpg://...")
registry = saffier.Registry(database=database)


class AutoUsers(AutoReflectModel):
    class Meta:
        registry = registry
        include_pattern = r"^users$"
```

Then call:

```python
await registry.reflect_pattern_models()
```

Generated reflected models become available in `registry.reflected`.

## Pattern options

- `include_pattern`: regex that must match `table.name`.
- `exclude_pattern`: regex to exclude matching tables.
- `template`: name template (string) or callable receiving SQLAlchemy `Table`.
- `databases`: database names where this pattern applies (`None` for primary).
- `schemes`: schemas where this pattern applies (`None` for default schema).

## Important notes

- Pattern classes are treated as admin/infrastructure declarations and are not normal concrete ORM
  models.
- Saffier keeps this feature Python-native and does not depend on Pydantic schema generation.
