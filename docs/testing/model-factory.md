# Model Factory

Saffier ships testing factories in `saffier.testing` for building model instances without writing
large setup payloads by hand. Factories are Python-native and work with Saffier models, validators,
relationship fields, and the SQLAlchemy Async runtime used by the test client.

Install the testing extra when your project does not already include the factory dependencies.

```shell
pip install "saffier[testing]"
```

## Basic Factory

Define a `ModelFactory` subclass and point `Meta.model` at the Saffier model.

```python
{!> ../docs_src/testing/factory/basic.py !}
```

Passing keyword arguments to the factory instance overrides generated values. `build()` returns a
model instance marked as loaded, but it does not write to the database.

## Factory Fields

Use `FactoryField` for generated values. A string callback calls the matching Faker method. A
callable callback receives the field, the factory context, and field-specific parameters.

```python
from saffier.testing import FactoryField


class UserFactory(ModelFactory):
    class Meta:
        model = User

    name = FactoryField(callback="name")
```

`FactoryField(parameters=...)` lets you pass default faker parameters. Build-time `parameters`
override or extend those defaults for one generated object.

## Relationships

Use `SubFactory` for one related object and `ListSubFactory` or
`ModelFactory.to_list_factory_field(...)` for repeated related values.

```python
{!> ../docs_src/testing/factory/relations.py !}
```

This keeps relationship construction inside the same factory context, including call counts and
faker state.

## Persisting Rows

Use `build_and_save()` in async tests when you want a row in the database. It uses Saffier's normal
model save path and works well with `DatabaseTestClient.force_rollback()`.

```python
{!> ../docs_src/testing/factory/save.py !}
```

Prefer `build_and_save()` over `build(save=True)` in async tests. The explicit async method avoids
surprising nested-loop behavior and makes transaction ownership clear.

## Useful Build Options

`build(...)` and `build_and_save(...)` accept:

* `parameters`: per-field generator parameters.
* `overwrites`: direct field values that bypass generation.
* `exclude`: fields to omit from generated payloads.
* `database`: database object to attach to the built model.
* `schema`: schema name to attach to the built model.
* `exclude_autoincrement`: whether autoincrement primary keys are generated.
* `callcounts`: custom call-count storage for deterministic sequences.

The factory context exposes `faker`, `exclude_autoincrement`, `depth`, and `callcounts`. Custom
callbacks can also store extra context keys as long as they do not collide with those built-in
names.
