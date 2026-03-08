# `Schema`

`Schema` is the registry helper that performs database-schema operations such as
creating and dropping schemas.

It matters most in multi-schema and multi-tenant deployments where the
application needs to provision or tear down schema-scoped tables explicitly.

## Typical use

Most application code reaches `Schema` through the registry:

```python
await models.schema.create_schema("tenant_a", if_not_exists=True)
await models.schema.drop_schema("tenant_a", cascade=True, if_exists=True)
```

## Important distinction

This helper manages *database schemas*, not Saffier model field schemas or JSON
schemas.

::: saffier.core.connection.schemas.Schema
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
