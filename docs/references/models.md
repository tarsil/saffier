# `Model`

`Model` is the default base class for application-facing Saffier ORM models.

Use it when you want Saffier to manage persistence, lazy relation loading,
signal emission, and serialization through declared fields.

## What `Model` is responsible for

`Model` adds the persistence lifecycle on top of the lower-level base model:

* `save()` decides between insert and update flows
* `update()` validates and persists partial changes
* `delete()` emits signals and runs relation cleanup
* `load()` refreshes the current instance from the database
* `model_dump()` serializes declared fields instead of raw `__dict__`
* optional engine helpers project the model into an external adapter without changing ORM semantics

## Typical lifecycle

```python
user = User(name="Ada", email="ada@example.com")
await user.save()

user.name = "Ada Lovelace"
await user.save(values={"name": user.name})

fresh = await User.query.get(pk=user.pk)
payload = fresh.model_dump()
```

## Important behaviors

* Undeclared `id` primary keys are auto-generated for normal models.
* Related objects can be passed directly to foreign-key fields and are saved
  first when needed.
* Reverse relations staged through `tracks_set=[...]` style payloads are
  persisted after the parent model has been saved.
* `model_dump()` respects field options such as `exclude=True` and skips
  many-to-many managers.

## When to use something else

Use [`StrictModel`](./strict-model.md) if you want runtime assignment
validation and rejection of undeclared public attributes.

Use [`ReflectModel`](./reflect-model.md) if the table already exists and should
be reflected from the database instead of generated from field declarations.

Use [Model Engines](../engines.md) when you want an optional engine-backed
projection such as Pydantic on top of the normal Saffier model.

::: saffier.Model
    options:
        filters:
        - "!^model_config"
        - "!^__dict__"
        - "!^__repr__"
        - "!^__str__"
