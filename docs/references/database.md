# `Database`

`Database` is Saffier's database connection wrapper.

Most applications interact with it indirectly through a `Registry`, but the
class is still important because it defines connection lifecycle, transaction
management, and the SQLAlchemy async engine used by queries and schema helpers.

## Typical usage

```python
database = saffier.Database(
    "postgresql+asyncpg://postgres:postgres@localhost:5432/app"
)
models = saffier.Registry(database=database)
```

## What to know in practice

* prefer `saffier.Database`, not the `databases` package object
* registry lifecycle usually controls `connect()` and `disconnect()`
* synchronous reflection paths use the wrapped sync engine derived from the
  async engine

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
