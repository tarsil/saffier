from __future__ import annotations

import copy
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from saffier.conf.functional import LazyObject, empty
from saffier.conf.module_import import import_string

if TYPE_CHECKING:
    from saffier.conf.global_settings import SaffierSettings

ENVIRONMENT_VARIABLE = "SAFFIER_SETTINGS_MODULE"
DEFAULT_SETTINGS_MODULE = "saffier.conf.global_settings.SaffierSettings"


class SaffierLazySettings(LazyObject):
    """
    A lazy proxy for either global Saffier settings or a custom settings object.
    The user can manually configure settings prior to using them. Otherwise,
    Saffier uses the settings module pointed to by SAFFIER_SETTINGS_MODULE.
    """

    def _resolve(
        self, settings_value: str | type[SaffierSettings] | SaffierSettings | None = None
    ) -> SaffierSettings:
        from saffier.conf.global_settings import SaffierSettings

        configured = settings_value or os.environ.get(
            ENVIRONMENT_VARIABLE, DEFAULT_SETTINGS_MODULE
        )

        if isinstance(configured, SaffierSettings):
            settings_instance = configured
        else:
            if isinstance(configured, str):
                settings_class = import_string(configured)
            else:
                settings_class = configured
            settings_instance = settings_class()

        for setting in settings_instance.dict():
            assert setting.islower(), f"{setting} should be in lowercase."

        return settings_instance

    def _setup(self, name: str | None = None) -> None:
        """
        Load the settings module pointed to by the environment variable. This
        is used the first time settings are needed, if the user hasn't
        configured settings manually.
        """
        self._wrapped = self._resolve()

    def __repr__(self: SaffierLazySettings) -> str:
        # Hardcode the class name as otherwise it yields 'SaffierSettings'.
        if self._wrapped is empty:
            return "<SaffierLazySettings [Unevaluated]>"
        return f'<SaffierLazySettings "{self._wrapped.__class__.__name__}">'

    def configure(
        self,
        settings_value: str | type[SaffierSettings] | SaffierSettings | None = None,
        **overrides: Any,
    ) -> SaffierSettings:
        """
        Eagerly configure Saffier settings from a dotted path, class, or instance.
        Optional keyword overrides are applied on top of the resolved settings object.
        """
        resolved = self._resolve(settings_value)
        for key, value in overrides.items():
            setattr(resolved, key, value)
        self._wrapped = resolved
        return resolved

    def reload(self) -> SaffierSettings:
        """
        Reload settings from `SAFFIER_SETTINGS_MODULE`.
        """
        self._wrapped = self._resolve(
            os.environ.get(ENVIRONMENT_VARIABLE, DEFAULT_SETTINGS_MODULE)
        )
        return self._wrapped

    @contextmanager
    def override(self, **overrides: Any) -> Iterator[SaffierSettings]:
        """
        Temporarily override setting values.
        """
        previous = self._wrapped
        current = self._resolve() if previous is empty else copy.deepcopy(previous)
        for key, value in overrides.items():
            setattr(current, key, value)
        self._wrapped = current
        try:
            yield current
        finally:
            self._wrapped = previous

    @property
    def configured(self) -> Any:
        """Return True if the settings have already been configured."""
        return self._wrapped is not empty


_lazy_settings = SaffierLazySettings()
settings: SaffierSettings = cast("SaffierSettings", _lazy_settings)


def configure_settings(
    settings_value: str | type[SaffierSettings] | SaffierSettings | None = None,
    **overrides: Any,
) -> SaffierSettings:
    """
    Configure global Saffier settings.
    """
    return _lazy_settings.configure(settings_value, **overrides)


def reload_settings() -> SaffierSettings:
    """
    Reload global Saffier settings from `SAFFIER_SETTINGS_MODULE`.
    """
    return _lazy_settings.reload()


@contextmanager
def override_settings(**overrides: Any) -> Iterator[SaffierSettings]:
    """
    Temporarily override global Saffier settings.
    """
    with _lazy_settings.override(**overrides) as configured:
        yield configured


__all__ = [
    "DEFAULT_SETTINGS_MODULE",
    "ENVIRONMENT_VARIABLE",
    "SaffierLazySettings",
    "configure_settings",
    "override_settings",
    "reload_settings",
    "settings",
]
