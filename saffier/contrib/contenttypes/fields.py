from __future__ import annotations

from typing import Any

from saffier.core.db.constants import CASCADE
from saffier.core.db.fields.base import ForeignKey
from saffier.core.terminal import Print

terminal = Print()


class ContentTypeField(ForeignKey):
    def __init__(
        self,
        to: type[Any] | str = "ContentType",
        on_delete: str = CASCADE,
        **kwargs: Any,
    ) -> None:
        for argument in ("unique", "null"):
            if argument in kwargs:
                terminal.write_warning(
                    f"Declaring `{argument}` on a ContentTypeField has no effect."
                )

        kwargs["unique"] = True
        kwargs["null"] = False
        super().__init__(
            to=to,
            on_delete=on_delete,
            **kwargs,
        )

    def expand_relationship(self, value: Any) -> Any:
        if isinstance(value, dict):
            return self.target(**value)
        return super().expand_relationship(value)
