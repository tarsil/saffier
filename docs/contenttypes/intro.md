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

## Default Behavior

```python
class Company(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
```

Each `Company` instance receives its own `content_type` row.

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
