from __future__ import annotations

from typing import Any

from saffier.conf.module_import import import_string

from .fields import FactoryField


class SubFactory(FactoryField):
    def __init__(self, factory: Any, **kwargs: Any) -> None:
        self.factory = factory
        super().__init__(callback=self._callback, **kwargs)

    def _callback(
        self, field: FactoryField, context: dict[str, Any], parameters: dict[str, Any]
    ) -> Any:
        if isinstance(self.factory, str):
            self.factory = import_string(self.factory)
        factory = self.factory() if isinstance(self.factory, type) else self.factory
        return factory.build(**parameters)


class ListSubFactory(FactoryField):
    def __init__(self, factory: Any, *, min: int = 0, max: int = 3, **kwargs: Any) -> None:
        self.factory = factory
        self.min = min
        self.max = max
        super().__init__(callback=self._callback, **kwargs)

    def _callback(
        self, field: FactoryField, context: dict[str, Any], parameters: dict[str, Any]
    ) -> Any:
        min_value = parameters.pop("min", self.min)
        max_value = parameters.pop("max", self.max)
        size = context["faker"].random_int(min=min_value, max=max_value)
        if isinstance(self.factory, str):
            self.factory = import_string(self.factory)
        factory = self.factory() if isinstance(self.factory, type) else self.factory
        return [factory.build(**parameters) for _ in range(size)]
