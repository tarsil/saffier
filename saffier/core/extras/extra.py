from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from saffier.cli.constants import SAFFIER_DB, SAFFIER_EXTRA
from saffier.core.extras.base import BaseExtra
from saffier.core.terminal import Print, Terminal

if TYPE_CHECKING:
    from saffier.core.connection.registry import Registry

object_setattr = object.__setattr__
terminal = Terminal()
printer = Print()


@dataclass
class Config:
    app: Any
    registry: "Registry"


class SaffierExtra(BaseExtra):
    def __init__(self, app: Any, registry: "Registry", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.app = app
        self.registry = registry

        self.set_saffier_extension(self.app, self.registry)

    def set_saffier_extension(self, app: Any, registry: "Registry") -> None:
        """
        Sets a saffier dictionary for the app object.
        """
        if hasattr(app, SAFFIER_DB):
            printer.write_warning(
                "The application already has a Migrate related configuration with the needed information. SaffierExtra will be ignored and it can be removed."
            )
            return

        config = Config(app=app, registry=registry)
        object_setattr(app, SAFFIER_EXTRA, {})
        app._saffier_extra["extra"] = config
