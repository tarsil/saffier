from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from saffier.core.extras.base import BaseExtra

if TYPE_CHECKING:
    from saffier.core.registry import Registry

object_setattr = object.__setattr__


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
        config = Config(app=app, registry=registry)
        object_setattr(app, "_saffier_extra", {})
        app._saffier_extra["extra"] = config
