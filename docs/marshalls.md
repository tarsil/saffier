# Marshalls

Saffier marshalls are model-backed serializers and data transfer objects.

They provide:

* controlled output via `model_dump()`
* Python-native input validation for marshall-specific fields
* computed and sourced fields
* partial update workflows
* a `save()` bridge back into Saffier models

Unlike Edgy, Saffier marshalls are **not** Pydantic models. They are implemented directly on top
of Saffier’s field and model system, which keeps the subsystem Python-native and avoids introducing
Pydantic as a framework dependency.

## Imports

Use any of the following:

```python
import saffier

from saffier import ConfigMarshall, Marshall, MarshallField, MarshallMethodField
from saffier import marshalls
from saffier.core.marshalls import ConfigMarshall, Marshall
```

The public `saffier.marshalls` namespace mirrors the core marshall API:

```python
from saffier import marshalls

marshalls.Marshall
marshalls.MarshallField
marshalls.MarshallMethodField
```

## Basic Example

```python
from typing import ClassVar

import saffier


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    email = saffier.EmailField(max_length=100, null=True)


class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name", "email"],
    )
    display_name = saffier.MarshallField(str, source="name")
    details = saffier.MarshallMethodField(str)

    def get_details(self, instance: User) -> str:
        return f"Display name: {instance.name}"


payload = UserMarshall(name="Saffier", email="saffier@ravyn.dev")
payload.model_dump()
```

Result:

```json
{
  "name": "Saffier",
  "email": "saffier@ravyn.dev",
  "display_name": "Saffier",
  "details": "Display name: Saffier"
}
```

## `marshall_config`

Every marshall must define `marshall_config`.

Supported keys:

* `model`: a Saffier model class or dotted import string
* `fields`: included model field names
* `exclude`: excluded model field names
* `primary_key_read_only`: mark selected primary keys as read-only
* `exclude_autoincrement`: remove autoincrement primary keys from the marshall
* `exclude_read_only`: remove read-only model fields from the marshall

Rules:

* declare `fields` or `exclude`, not both
* `model` is mandatory
* if `marshall_config` is annotated, use `ClassVar[...]`

Example:

```python
class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["__all__"],
        exclude_autoincrement=True,
    )
```

`"__all__"` includes all selected model fields in the marshall.

## Marshall Fields

Saffier supports two marshall-specific field types.

### `MarshallField`

Use this when the value should come from:

* a model attribute
* a model property
* a model method with no arguments
* a marshall-local control field

```python
class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name"],
    )
    upper_name = saffier.MarshallField(str, source="upper_name")
```

Parameters:

* `field_type`: expected Python type
* `source`: alternate attribute/property/method name on the model instance
* `allow_null`: allow `None`
* `default`: static or callable default
* `exclude`: keep the field on the marshall but remove it from `model_dump()`

`exclude=True` is the Saffier-native way to declare marshall-local control fields:

```python
class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name"],
    )
    shall_save = saffier.MarshallField(bool, default=False, exclude=True)
```

### `MarshallMethodField`

Use this when the value should come from logic defined on the marshall itself.

```python
class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name"],
    )
    details = saffier.MarshallMethodField(str)

    def get_details(self, instance: User) -> str:
        return f"User: {instance.name}"
```

Rules:

* define `get_<field_name>()`
* the method receives the current model instance
* async getters are supported

## Context

Marshalls accept an optional `context` dictionary.

```python
class UserMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["name"],
    )
    extra_context = saffier.MarshallMethodField(dict[str, str])

    def get_extra_context(self, instance: User) -> dict[str, str]:
        return self.context


payload = UserMarshall(name="Saffier", context={"source": "admin"})
payload.model_dump()
```

## Partial Marshalls

You can declare a marshall with only part of the model fields and attach the instance later.

```python
class EmailUpdateMarshall(saffier.Marshall):
    marshall_config: ClassVar[saffier.ConfigMarshall] = saffier.ConfigMarshall(
        model=User,
        fields=["email"],
    )


payload = EmailUpdateMarshall(email="new@ravyn.dev")
payload.instance = await User.query.get(pk=1)
await payload.save()
```

If required model fields are missing and no instance is attached, accessing `instance` or calling
`save()` raises a runtime error.

## Saving

`await marshall.save()` persists the associated model.

Creation:

```python
payload = UserMarshall(name="Saffier", email="saffier@ravyn.dev")
await payload.save()
```

Update:

```python
user = await User.query.get(pk=1)
payload = UserMarshall(instance=user)
payload.name = "Updated"
await payload.save()
```

Behavior:

* if the marshall was built from raw values, Saffier creates a model instance and saves it
* if the marshall was built from an existing instance, Saffier updates that instance
* autoincrement primary keys are synchronized back into the marshall after save

## Dumping And Schema Output

Use `model_dump()` to serialize the marshall:

```python
payload.model_dump()
payload.model_dump(exclude_none=True)
payload.model_dump(exclude_unset=True)
```

Use `model_json_schema()` for a lightweight JSON-schema-style description of the current marshall
surface:

```python
UserMarshall.model_json_schema()
```

This is intentionally simpler than Pydantic’s schema system. It is designed for inspection,
tooling, and admin-style form generation, not for full Pydantic compatibility.

## Relationship Guidance

Marshalls are strongest for scalar model data and computed output.

For relationships, especially nested foreign keys and many-to-many data, prefer explicit marshall
fields instead of relying on implicit object serialization. This keeps output predictable and
matches Saffier’s Python-native design.

## Error Cases

Common configuration errors raise `MarshallFieldDefinitionError`:

* missing `marshall_config`
* using both `fields` and `exclude`
* omitting both `fields` and `exclude`
* forgetting `ClassVar` on annotated `marshall_config`
* declaring a `MarshallMethodField` without `get_<name>()`
