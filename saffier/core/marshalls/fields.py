from __future__ import annotations

from typing import Any, ClassVar

_UNSET = object()


class BaseMarshallField:
    __is_method__: ClassVar[bool] = False

    def __init__(
        self,
        field_type: Any,
        source: str | None = None,
        allow_null: bool = False,
        default: Any = _UNSET,
        *,
        exclude: bool = False,
        title: str = "",
        description: str = "",
        help_text: str = "",
    ) -> None:
        self.name: str = ""
        self.field_type = field_type
        self.source = source
        self.null = allow_null
        self.exclude = exclude
        self.title = title
        self.description = description
        self.help_text = help_text
        if default is not _UNSET:
            self.default = default
        elif self.null:
            self.default = None

    def has_default(self) -> bool:
        return hasattr(self, "default")

    def get_default_value(self) -> Any:
        default = getattr(self, "default", None)
        if callable(default):
            return default()
        return default

    def is_required(self) -> bool:
        return not self.null and not self.has_default()

    def validate(self, value: Any) -> Any:
        if value is None:
            if self.null or self.has_default():
                return None if not self.has_default() else self.get_default_value()
            raise TypeError(f"{self.name or 'value'} may not be null.")
        return value


class MarshallMethodField(BaseMarshallField):
    __is_method__: ClassVar[bool] = True

    def __init__(self, field_type: Any, **kwargs: Any) -> None:
        kwargs.pop("default", None)
        kwargs.pop("source", None)
        kwargs.pop("allow_null", None)
        super().__init__(field_type, source=None, allow_null=True, default=None, **kwargs)


class MarshallField(BaseMarshallField):
    def __init__(
        self,
        field_type: Any,
        source: str | None = None,
        allow_null: bool = True,
        default: Any = _UNSET,
        **kwargs: Any,
    ) -> None:
        if default is _UNSET and allow_null:
            default = None
        super().__init__(
            field_type,
            source=source,
            allow_null=allow_null,
            default=default,
            **kwargs,
        )


__all__ = ["BaseMarshallField", "MarshallField", "MarshallMethodField"]
