# Registry

When using the **Saffier** ORM, you must use the **Registry** object to tell exactly where the
database is going to be.

Imagine the registry as a mapping between your models and the database where is going to be written.

And is just that, nothing else and very simple but effective object.

The registry is also the object that you might want to use when generating migrations using
Alembic.

```python hl_lines="19"
{!> ../docs_src/registry/model.py !}
```

## Parameters

* **database** - An instance of `saffier.core.db.Database` object.

!!! Warning
    Using the `Database` from the `databases` package will raise an assertation error. You must
    use the `saffier.Database` object instead.

* **schema** - The schema to connect to. This can be very useful for multi-tenancy applications if
you want to specify a specific schema or simply if you just want to connect to a different schema
that is not the default.

    ```python
    from saffier import Registry

    registry = Registry(database=..., schema="custom-schema")
    ```

## Custom registry

Can you have your own custom Registry? Yes, of course! You simply need to subclass the `Registry`
class and continue from there like any other python class.

```python hl_lines="15 29"
{!> ../docs_src/registry/custom_registry.py !}
```

## Multiple registries

Sometimes you might want to work with multiple databases across different functionalities and
that is also possible thanks to the registry with [Meta](./models.md#the-meta-class) combination.

```python hl_lines="26 33"
{!> ../docs_src/registry/multiple.py !}
```

When you use the `extra=` mapping for multiple databases, keep the keys stable and string-based.
Saffier preserves a separate SQLAlchemy `MetaData` object per configured database and exposes both
`metadata_by_name` and `metadata_by_url` for migration/runtime code that needs to target a specific
connection.

Names with surrounding whitespace still work, but Saffier warns about them because they make CLI
and migration output harder to read.

## Copying a Registry

Migration workflows sometimes need an isolated copy of the registry instead of mutating the active
application registry in place.

```python
import copy

import saffier


registry_copy = copy.copy(models)
prepared_copy = saffier.get_migration_prepared_registry(registry_copy)
```

The copied registry keeps:

* per-database metadata mappings
* reflected-model metadata refresh behavior
* copied many-to-many through models wired to the copied registry

That makes it safe to prepare migration metadata without leaving copied relationship state attached
to the original registry.

## Dynamic model registration

Saffier models can also be copied and attached to another registry at runtime.

```python
user_copy = User.copy_saffier_model()
tenant_user = user_copy.add_to_registry(tenant_registry)
```

This is useful for migration preparation, extension-driven model composition, and tests that need
isolated registries. If a copied model still references models that are added later, Saffier now
defers the reverse-relation wiring until those models are registered in the target registry.

## Automigration

For managed runtimes, a registry can also opt into running migrations on first connect:

```python
from saffier import Registry
from myproject.configs.settings import Settings


registry = Registry(database=database, automigrate_config=Settings)
```

This delegates to the normal migration `upgrade()` flow and is still controlled by
`settings.allow_automigrations`.

## Schemas

This is another great supported feature from Saffier. This allows you to manipulate database schema
operations like [creating schemas](#create-schema) or [dropping schemas](#drop-schema).

This can be particulary useful if you want to create a [multi-tenancy](./tenancy/saffier.md) application
and you need to generate schemas for your own purposes.

### Create schema

As the name suggests, it is the functionality that allows you to create database schemas.

**Parameters**:

* **schema** - String name of the schema.
* **if_not_exists** - Flag indicating if should create if not exists.

    <sup>Default: `False`</sup>

```python hl_lines="11"
{!> ../docs_src/registry/create_schema.py !}
```

Create a schema called `saffier`.

```python
await create_schema("saffier")
```

This will make sure it will create a new schema `saffier` if it does not exist. If the `if_not_exists`
is `False` and the schema already exists, it will raise a `saffier.exceptions.SchemaError`.

### Drop schema

As name also suggests, it is the opposite of [create_schema](#create-schema) and instead of creating
it will drop it from the database.

!!! Warning
    You need to be very careful when using the `drop_schema` as the consequences are irreversible
    and not only you don't want to remove the wrong schema but also you don't want to delete the
    `default` schema as well. Use it with caution.

**Parameters**:

* **schema** - String name of the schema.
* **cascade** - Flag indicating if should do `cascade` delete.
*
    <sup>Default: `False`</sup>

* **if_exists** - Flag indicating if should create if not exists.

    <sup>Default: `False`</sup>

```python hl_lines="11"
{!> ../docs_src/registry/drop_schema.py !}
```

Drop a schema called `saffier`

```python
await drop_schema("saffier")
```

This will make sure it will drop a schema `saffier` if exists. If the `if_exists`
is `False` and the schema does not exist, it will raise a `saffier.exceptions.SchemaError`.

### Get default schema name

This is just a helper. Each database has its own ***default*** schema name, for example,
Postgres calls it `public` and MSSQLServer calls it `dbo`.

This is just an helper in case you need to know the default schema name for any needed purpose of
your application.

```python hl_lines="11"
{!> ../docs_src/registry/default_schema.py !}
```

## Extra

{!> ../docs_src/shared/extra.md !}
