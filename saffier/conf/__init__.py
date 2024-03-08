import os
from typing import TYPE_CHECKING, Any, Optional, Type

from saffier.conf.functional import LazyObject, empty
from saffier.conf.module_import import import_string

if TYPE_CHECKING:
    from saffier.conf.global_settings import SaffierSettings

ENVIRONMENT_VARIABLE = "SAFFIER_SETTINGS_MODULE"


class SaffierLazySettings(LazyObject):
    """
    A lazy proxy for either global Saffier settings or a custom settings object.
    The user can manually configure settings prior to using them. Otherwise,
    Saffier uses the settings module pointed to by LILYA_SETTINGS_MODULE.
    """

    def _setup(self, name: Optional[str] = None) -> None:
        """
        Load the settings module pointed to by the environment variable. This
        is used the first time settings are needed, if the user hasn't
        configured settings manually.
        """
        settings_module: str = os.environ.get(
            ENVIRONMENT_VARIABLE, "saffier.conf.global_settings.SaffierSettings"
        )

        settings: Type["SaffierSettings"] = import_string(settings_module)

        for setting, _ in settings().dict().items():
            assert setting.islower(), "%s should be in lowercase." % setting

        self._wrapped = settings()

    def __repr__(self: "SaffierLazySettings") -> str:
        # Hardcode the class name as otherwise it yields 'SaffierSettings'.
        if self._wrapped is empty:
            return "<SaffierLazySettings [Unevaluated]>"
        return '<SaffierLazySettings "{settings_module}">'.format(
            settings_module=self._wrapped.__class__.__name__
        )

    @property
    def configured(self) -> Any:
        """Return True if the settings have already been configured."""
        return self._wrapped is not empty


settings: Type["SaffierSettings"] = SaffierLazySettings()  # type: ignore
