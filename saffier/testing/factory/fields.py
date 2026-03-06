from __future__ import annotations

from inspect import isclass
from typing import Any


class FactoryField:
    owner: Any
    original_name: str

    def __init__(
        self,
        *,
        exclude: bool = False,
        callback: Any = None,
        parameters: dict[str, Any] | None = None,
        field_type: str | type[Any] | None = None,
        name: str = "",
        no_copy: bool = False,
    ) -> None:
        self.exclude = exclude
        self.no_copy = no_copy
        self.name = name
        self.parameters = parameters or {}
        self.callback = callback
        self.field_type = field_type.__name__ if isclass(field_type) else (field_type or "")

    def resolve_callback(self) -> Any:
        if isinstance(self.callback, str):
            callback_name = self.callback
            return lambda _field, context, parameters: getattr(context["faker"], callback_name)(
                **parameters
            )
        return self.callback

    def resolve(
        self,
        context: dict[str, Any],
        callback: Any,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        resolved_parameters = dict(self.parameters)
        if parameters:
            resolved_parameters.update(parameters)
        for key, value in list(resolved_parameters.items()):
            if callable(value) and not isclass(value):
                resolved_parameters[key] = value(self, context, key)
        return callback(self, context, resolved_parameters)

    def __copy__(self) -> FactoryField:
        _copy = FactoryField(
            exclude=self.exclude,
            callback=self.callback,
            parameters=self.parameters.copy(),
            field_type=self.field_type,
            name=self.name,
            no_copy=self.no_copy,
        )
        if hasattr(self, "owner"):
            _copy.owner = self.owner
        if hasattr(self, "original_name"):
            _copy.original_name = self.original_name
        return _copy
