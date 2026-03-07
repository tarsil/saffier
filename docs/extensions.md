# Extensions

Saffier uses Monkay extensions for settings-driven runtime customization.

This is intentionally narrow in scope:

* extensions configure Saffier's runtime environment
* they do not replace the model layer
* they do not introduce Pydantic
* they operate against the active Monkay instance and active settings object

## Extension Protocol

A Saffier extension must follow the Monkay extension protocol.

That means it needs:

* a `name` attribute
* an `apply(self, monkay_instance)` method

```python title="myproject/extensions.py"
class ConfigureMedia:
    name = "configure-media"

    def apply(self, monkay_instance):
        monkay_instance.settings.media_root = "storage/media"
        monkay_instance.settings.media_url = "/media/"
```

## Registering Extensions in Settings

Import the extension class in your settings module and register it through `extensions`.

```python title="myproject/configs/settings.py"
from myproject.extensions import ConfigureMedia
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    extensions = (ConfigureMedia,)
```

Saffier registers these extensions when `evaluate_settings_once_ready()` is called.

## Working with the Active Instance

Extensions receive the Monkay instance, not a raw settings object and not a custom manager.

That gives you access to:

* `monkay_instance.settings`
* `monkay_instance.instance`

In Saffier, `monkay_instance.instance` is the currently active application context set by
`Migrate(...)` or `SaffierExtra(...)`.

Example:

```python title="myproject/extensions.py"
class CaptureRegistryInfo:
    name = "capture-registry-info"

    def apply(self, monkay_instance):
        instance = monkay_instance.instance
        if instance is None:
            return
        registry = instance.registry
        monkay_instance.settings.registry_model_count = len(registry.models)
```

## Preloads and Extensions

Preloads run before extensions are registered.

That matters because preload imports are the normal place where your project creates the app and
calls `Migrate(...)`.

Typical order:

1. `evaluate_settings_once_ready()` starts
2. preload module imports `myproject.main`
3. `myproject.main` wires `Migrate(app=..., registry=...)`
4. Saffier has an active Monkay instance
5. settings extensions are registered and applied to that instance

This is why `preloads = ("myproject.main",)` is the cleanest way to couple CLI discovery and
settings-based extensions.

## Dynamic Registration

You can also register an extension in code.

```python
from saffier import add_settings_extension, evaluate_settings_once_ready


class EnableDebugStorage:
    name = "enable-debug-storage"

    def apply(self, monkay_instance):
        monkay_instance.settings.media_root = "tmp/media"


add_settings_extension(EnableDebugStorage)
evaluate_settings_once_ready()
```

Use dynamic registration before the application is bootstrapped. That keeps extension application
predictable and avoids reapplying runtime hooks in an already-running process.

## Real-World Example

A Ravyn project might want to switch storage paths and stamp a few registry-derived values into
settings during startup.

```python title="myproject/extensions.py"
class ConfigureProjectRuntime:
    name = "configure-project-runtime"

    def apply(self, monkay_instance):
        monkay_instance.settings.media_root = "var/media"
        monkay_instance.settings.media_url = "/media/"

        instance = monkay_instance.instance
        if instance is not None:
            monkay_instance.settings.loaded_models = tuple(sorted(instance.registry.models))
```

```python title="myproject/configs/settings.py"
from myproject.extensions import ConfigureProjectRuntime
from saffier.conf.global_settings import SaffierSettings


class Settings(SaffierSettings):
    preloads = ("myproject.main",)
    extensions = (ConfigureProjectRuntime,)
```

## When to Use an Extension

Use an extension when you need to:

* configure runtime behavior after settings load
* inspect the active registry or application instance
* register environment-specific integrations around app startup

Do not use an extension when:

* a plain settings value is enough
* the behavior belongs in a model, field, or queryset abstraction
* the logic is request-specific instead of process-startup-specific

## See Also

* [Settings](./settings.md)
* [Application Discovery](./migrations/discovery.md)
* [Migrations](./migrations/migrations.md)
