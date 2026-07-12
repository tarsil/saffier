# `Database`

`Database` is Saffier's SQLAlchemy Async database runtime.

Most applications interact with it indirectly through a `Registry`, but the
class is still important because it defines connection lifecycle, transaction
management, and the SQLAlchemy `AsyncEngine`, `AsyncConnection`, and
`async_sessionmaker` used by queries and schema helpers.

## Typical usage

```python
database = saffier.Database(
    "postgresql+asyncpg://postgres:postgres@localhost:5432/app"
)
models = saffier.Registry(database=database)
```

## What to know in practice

* use `saffier.Database` for registry ownership and ORM execution
* registry lifecycle usually controls `connect()` and `disconnect()`
* advanced code can inspect the native SQLAlchemy async engine through
  `database.engine` after connection

::: saffier.Database
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
        - "!^__aenter__"
        - "!^__aexit__"
        - "!^SUPPORTED_BACKENDS"
        - "!^DIRECT_URL_SCHEME"
        - "!^MANDATORY_FIELDS"
