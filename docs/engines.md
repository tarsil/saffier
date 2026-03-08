# Model Engines

Saffier model engines are optional adapters that sit on top of the normal ORM model layer.

The important part is the direction of ownership:

* Saffier still owns fields, relations, defaults, validation hooks, identity, querysets, and database mapping.
* An engine only projects a Saffier model into another representation or validates external data before you turn it back into a Saffier model.
* If you do nothing, Saffier keeps working exactly as it does in pure Python mode.

## Why Saffier supports engines

Some applications want an extra model interface for:

* API-facing validation
* schema generation
* typed serialization
* interoperability with another Python model ecosystem

Saffier now supports that without making the ORM depend on any one engine.

## Core philosophy

Saffier is a Python-first, engine-agnostic ORM.

That means:

* the ORM is complete with no engine configured;
* query behavior does not change when you enable an engine;
* engine adapters consume Saffier model payloads instead of replacing Saffier models;
* future engines can be added by registration, not by changing core ORM semantics.

## Default mode: no engine

No configuration is required.

```python
import saffier


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
```

`User` keeps the normal Saffier lifecycle:

* `save()`
* `update()`
* `delete()`
* `load()`
* `model_dump()`

No engine-backed model is created unless you opt in.

## Configure a registry-wide engine

Use `Registry(model_engine=...)` when most models in one application should expose the same engine adapter.

```python
{!> ../docs_src/engines/registry_default.py !}
```

With that configuration:

* `user.to_engine_model()` returns the engine-backed representation;
* `User.engine_validate(data)` validates external data with the engine adapter;
* `User.from_engine(value)` turns an engine-backed value back into a normal Saffier model;
* `User.engine_json_schema()` exposes the engine-generated schema when the adapter supports it.

Today Saffier ships a built-in `pydantic` adapter.

## Per-model override and opt-out

Registry defaults are convenient, but not every model needs the same adapter.

```python
{!> ../docs_src/engines/per_model.py !}
```

Rules:

* `Meta.model_engine = "pydantic"` selects one named adapter for that model.
* `Meta.model_engine = False` disables the registry default for that model.
* If `Meta.model_engine` is omitted, the registry default is used.

This makes gradual adoption practical: turn an engine on for one model, one app, or one registry at a time.

## Pydantic example

The built-in Pydantic adapter is intentionally layered on top of Saffier.

```python
payload = User.engine_validate({"name": "Ada", "email": "ada@example.com"})
user = User.from_engine(payload)

engine_user = user.to_engine_model()
engine_user.model_dump(exclude_unset=True)
# {"name": "Ada", "email": "ada@example.com"}

user.engine_dump()
user.engine_dump_json()
User.engine_json_schema(mode="validation")
```

Two modes matter:

* `projection` mode is used by `to_engine_model()` and `engine_dump()`. It reflects whatever the Saffier instance currently has loaded.
* `validation` mode is used by `engine_validate()`. It is intended for validating external input before you build a Saffier model.

## Custom engine adapters

Custom adapters inherit from `saffier.ModelEngine` and register themselves by name.

```python
import saffier


class AttrsLikeEngine(saffier.ModelEngine):
    name = "attrs-like"

    def get_model_class(self, model_class, *, mode="projection"):
        return dict

    def validate_model(self, model_class, value, *, mode="validation"):
        return dict(value)

    def to_saffier_data(self, model_class, value, *, exclude_unset=False):
        return dict(value)

    def json_schema(self, model_class, *, mode="projection", **kwargs):
        return {"title": model_class.__name__, "mode": mode}


saffier.register_model_engine("attrs-like", AttrsLikeEngine())
```

Then attach it through `Registry(model_engine="attrs-like")` or `Meta.model_engine = "attrs-like"`.

The adapter contract is intentionally small:

* build or return an engine-backed class;
* validate/project values into that representation;
* convert that representation back into Saffier constructor data;
* optionally expose schemas.

## Future engines and extension points

The built-in architecture is deliberately generic enough for adapters such as:

* `msgspec`
* `attrs`
* project-specific dataclass or schema systems

Those integrations do not require changing Saffier querysets, fields, or persistence flows. They only need an adapter that consumes Saffier-owned model definitions and payloads.

## Guarantees

Saffier guarantees:

* core ORM semantics stay engine-independent;
* no engine is required for normal model usage;
* enabling an engine does not change queryset, relation, or save/load behavior;
* engine-backed representations are projections of Saffier models, not replacements for them.

## Limitations

Current limits are intentional:

* Saffier ships one built-in adapter today: `pydantic`.
* Relation projection is serialization-oriented. Saffier still owns relation loading and identity.
* Engine methods are opt-in APIs. Existing code that only uses normal Saffier models does not need to change.

## Migration guidance

For existing projects:

1. Keep current models unchanged if you do not need an engine.
2. If you want one engine across an app, add `model_engine="pydantic"` to the registry.
3. If you want a gradual rollout, set `Meta.model_engine = "pydantic"` only on selected models.
4. If a registry has a default engine and one model should stay pure Saffier, use `Meta.model_engine = False`.

The core rule stays the same throughout migration: Saffier models remain the source of truth.
