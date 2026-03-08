# `Registry`

`Registry` is the runtime hub for model registration and database ownership.

If models are the shape of your application data, the registry is the runtime
environment that tells those models where they live and how metadata should be
built.

## Core responsibilities

* own the primary database and any `extra` databases
* register declared, reflected, and pattern-generated models
* expose SQLAlchemy metadata for migrations and table building
* copy model definitions into isolated registries when needed
* coordinate content types, schema helpers, and reflection callbacks

## Practical example

```python
database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database)
```

## Runtime patterns to know

`copy.copy(registry)` is a supported workflow for migration preparation and
test isolation.

`with_async_env()` exists for synchronous scripts or CLI-style code that still
needs the registry lifecycle managed correctly.

`metadata_by_name` and `metadata_by_url` matter when a project uses `extra=`
databases and migration/runtime code needs the correct SQLAlchemy metadata
container for each connection.

::: saffier.Registry
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
