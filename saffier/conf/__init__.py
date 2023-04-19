import os
from typing import Any, Optional, Type

from saffier.conf.functional import LazyObject, empty
from saffier.conf.module_import import import_string

ENVIRONMENT_VARIABLE = "SAFFIER_SETTINGS_MODULE"

DBSettings = Type["SaffierLazySettings"]


class SaffierLazySettings(LazyObject):
    def _setup(self, name: Optional[str] = None) -> None:
        """
        Load the settings module pointed to by the environment variable. This
        is used the first time settings are needed, if the user hasn't
        configured settings manually.
        """
        settings_module: str = os.environ.get(
            ENVIRONMENT_VARIABLE, "saffier.conf.global_settings.SaffierSettings"
        )
        settings: Any = import_string(settings_module)

        for setting, _ in settings().dict().items():
            assert setting.islower(), "%s should be in lowercase." % setting

        self._wrapped = settings()

    def __repr__(self: "SaffierLazySettings"):
        # Hardcode the class name as otherwise it yields 'Settings'.
        if self._wrapped is empty:
            return "<SaffierLazySettings [Unevaluated]>"
        return '<SaffierLazySettings "{settings_module}">'.format(
            settings_module=self._wrapped.__class__.__name__
        )

    @property
    def configured(self):
        """Return True if the settings have already been configured."""
        return self._wrapped is not empty


settings: DBSettings = SaffierLazySettings()
