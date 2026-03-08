# Managers

Managers are the bridge between model classes and querysets.

If a model is the description of a table, a manager is the entry point that
decides which queryset object to hand back for that model and in which context
that queryset should run.

## Default behavior

Every concrete model gets a default `query` manager.

Managers in Saffier are descriptors, so they behave differently depending on
where you access them:

* on the model class, they are class-bound
* on a model instance, they are shallow-copied and instance-bound

That instance binding matters when schema selection or database selection comes
from the current model instance.

```python
{!> ../docs_src/models/managers/simple.py !}
```

## When to create a custom manager

Create a custom manager when you want:

* a reusable default filter such as “only active rows”
* project-specific query helpers kept close to the model
* a specialized queryset class for one family of models

The usual pattern is to subclass `saffier.Manager` and override
`get_queryset()`.

```python
{!> ../docs_src/models/managers/custom.py !}
```

In real projects this is useful for things like:

* hiding soft-deleted rows by default
* adding tenant scoping rules
* exposing common helper methods such as `published()` or `for_account()`

## Practical pattern: multiple managers on the same model

It is often better to keep `query` unfiltered and add an extra filtered manager
instead of replacing the default manager immediately.

```python
class User(saffier.Model):
    query: ClassVar[saffier.Manager] = saffier.Manager()
    active: ClassVar[ActiveUsersManager] = ActiveUsersManager()
```

That gives you both:

* `await User.query.all()` for the full table
* `await User.active.all()` for the opinionated subset

## Overriding the default manager

Overriding `query` is supported, but it changes the semantics of every normal
query entry point for that model.

```python
{!> ../docs_src/models/managers/override.py !}
```

!!! Warning
    If you override `query` with a filtered manager, `all()`, `get()`, `count()`,
    and related helpers all inherit that filter. Keep an unfiltered manager
    available somewhere if your application still needs raw access.
