# Content Types

Saffier provides a Python-native `contenttypes` contrib for generic model references.

## Enable Content Types

Enable content types in your registry:

```python
import saffier

database = saffier.Database("postgresql+asyncpg://...")
models = saffier.Registry(database=database, with_content_type=True)
```

When enabled:

* Saffier registers a concrete `ContentType` model in the registry.
* Regular models get an auto-managed `content_type` relation unless they opt out.
* `ContentType` records are created automatically on save.
* Tenant models store their active schema in `ContentType.schema_name`, so
  `await content_type.get_instance()` resolves back into the correct tenant schema.

## Default Behavior

```python
class Company(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
```

Each `Company` instance receives its own `content_type` row.

## Custom Content Type Models

You can provide either an abstract or a concrete content type model:

```python
from saffier.contrib.contenttypes.models import ContentType as BaseContentType


class CustomContentType(BaseContentType):
    marker = saffier.CharField(max_length=1, null=True)

    class Meta:
        abstract = True


models = saffier.Registry(database=database, with_content_type=CustomContentType)
```

Concrete custom models are reused directly. Abstract custom models are turned into a concrete
registry-local `ContentType` model.

## Shared Content Type Registries

Saffier can also point one registry at another registry's content type model:

```python
shared = saffier.Registry(database=other_database, with_content_type=True)
models = saffier.Registry(database=database, with_content_type=shared.content_type)
```

In that setup Saffier keeps the shared `ContentType` model instead of cloning it, disables the
database-level foreign key constraint where needed, and uses model-based deletes so removing shared
content type rows still removes the referencing Saffier models.

## Custom Content Type Field

If you need a custom field name, use `ContentTypeField` directly:

```python
from saffier.contrib.contenttypes import ContentTypeField


class Person(saffier.Model):
    name = saffier.CharField(max_length=100)
    c = ContentTypeField()

    class Meta:
        registry = models
```

## Opt-Out

To prevent automatic `content_type` injection for a model, reserve the name:

```python
class Tag(saffier.Model):
    content_type = saffier.ExcludeField()
    value = saffier.CharField(max_length=50)

    class Meta:
        registry = models
```

## API

* `saffier.contrib.contenttypes.ContentType`
* `saffier.contrib.contenttypes.ContentTypeField`
