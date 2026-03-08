from __future__ import annotations

import copy
import inspect
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, Literal, cast

from monkay import Monkay

from saffier.conf.base import BaseSettings, SettingsExtensionDefinition, SettingsExtensionProtocol
from saffier.conf.module_import import import_string
from saffier.core.events import is_async_callable

if TYPE_CHECKING:
    from saffier.conf.global_settings import SaffierSettings

ENVIRONMENT_VARIABLE = "SAFFIER_SETTINGS_MODULE"
DEFAULT_SETTINGS_MODULE = "saffier.conf.global_settings.SaffierSettings"

_monkay: Monkay[Any, SaffierSettings] = Monkay(
    globals(),
    settings_path=lambda: os.environ.get(ENVIRONMENT_VARIABLE, DEFAULT_SETTINGS_MODULE),
    with_instance=True,
    with_extensions=True,
    settings_preloads_name="preloads",
    settings_extensions_name="extensions",
    uncached_imports={"settings"},
)


def _reset_runtime_state() -> None:
    _monkay.set_instance(None, apply_extensions=False)
    _monkay._extensions.clear()


def _settings_payload(settings_instance: Any) -> dict[str, Any]:
    if hasattr(settings_instance, "dict") and callable(settings_instance.dict):
        values = settings_instance.dict()
        if isinstance(values, dict):
            payload = dict(values)
            payload.update(
                {
                    key: value
                    for key, value in vars(settings_instance).items()
                    if not key.startswith("_") and key not in payload
                }
            )
            return payload
    return {
        key: value for key, value in vars(settings_instance).items() if not key.startswith("_")
    }


def _resolve_settings(
    settings_value: str | type[SaffierSettings] | SaffierSettings | Any | None = None,
) -> SaffierSettings | Any:
    configured = settings_value
    if configured is None:
        configured = os.environ.get(ENVIRONMENT_VARIABLE, DEFAULT_SETTINGS_MODULE)

    if isinstance(configured, str):
        settings_class = import_string(configured)
        return settings_class()
    if inspect.isclass(configured):
        return configured()
    return configured


def _clone_settings(settings_instance: Any, **overrides: Any) -> Any:
    if not overrides:
        return settings_instance

    payload = _settings_payload(settings_instance)
    payload.update(overrides)

    try:
        return settings_instance.__class__(**payload)
    except TypeError:
        cloned = copy.deepcopy(settings_instance)
        for key, value in overrides.items():
            setattr(cloned, key, value)
        return cloned


class SettingsForward:
    def __getattribute__(self, name: str) -> Any:
        return getattr(_monkay.settings, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(_monkay.settings, name, value)


settings: SaffierSettings = cast("SaffierSettings", SettingsForward())


def configure_settings(
    settings_value: str | type[SaffierSettings] | SaffierSettings | Any | None = None,
    **overrides: Any,
) -> SaffierSettings | Any:
    configured = _clone_settings(_resolve_settings(settings_value), **overrides)
    _monkay.settings = configured
    _reset_runtime_state()
    return _monkay.settings


def reload_settings() -> SaffierSettings | Any:
    _monkay.settings = os.environ.get(ENVIRONMENT_VARIABLE, DEFAULT_SETTINGS_MODULE)
    _reset_runtime_state()
    return _monkay.settings


@contextmanager
def with_settings(
    settings_value: str | type[SaffierSettings] | SaffierSettings | Any | None = None,
    **overrides: Any,
) -> Iterator[SaffierSettings | Any]:
    configured = (
        _resolve_settings(settings_value) if settings_value is not None else _monkay.settings
    )
    with _monkay.with_settings(_clone_settings(configured, **overrides)):
        yield _monkay.settings


class override_settings:
    """Temporary settings override for tests and scoped execution blocks.

    The helper can be used as a synchronous or asynchronous context manager and
    also as a decorator for functions or coroutines.
    """

    def __init__(
        self,
        settings_value: str | type[SaffierSettings] | SaffierSettings | Any | None = None,
        **overrides: Any,
    ) -> None:
        self.settings_value = settings_value
        self.overrides = overrides
        self._innermanager: Any = None

    def __enter__(self) -> SaffierSettings | Any:
        self._innermanager = with_settings(self.settings_value, **self.overrides)
        return self._innermanager.__enter__()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._innermanager is not None:
            self._innermanager.__exit__(exc_type, exc_value, traceback)

    async def __aenter__(self) -> SaffierSettings | Any:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.__exit__(exc_type, exc_value, traceback)

    def __call__(self, func: Any) -> Any:
        if is_async_callable(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with self:
                    return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with self:
                return func(*args, **kwargs)

        return sync_wrapper


def evaluate_settings_once_ready() -> SaffierSettings | Any:
    evaluated_before = _monkay.settings_evaluated
    _monkay.evaluate_settings(
        on_conflict="replace",
        ignore_import_errors=False,
        ignore_preload_import_errors=False,
    )
    if not evaluated_before and _monkay.instance is not None:
        _monkay.apply_extensions()
    return _monkay.settings


def add_settings_extension(
    extension: SettingsExtensionDefinition,
    *,
    on_conflict: Literal["error", "keep", "replace"] = "replace",
) -> None:
    _monkay.add_extension(extension, on_conflict=on_conflict)


__all__ = [
    "DEFAULT_SETTINGS_MODULE",
    "ENVIRONMENT_VARIABLE",
    "BaseSettings",
    "SettingsExtensionDefinition",
    "SettingsExtensionProtocol",
    "add_settings_extension",
    "configure_settings",
    "evaluate_settings_once_ready",
    "override_settings",
    "reload_settings",
    "settings",
    "with_settings",
]
