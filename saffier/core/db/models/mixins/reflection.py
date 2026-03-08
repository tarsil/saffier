from __future__ import annotations

from typing import Any


class ReflectedModelMixin:
    __reflected__ = True

    @classmethod
    def real_add_to_registry(cls, **kwargs: Any):
        kwargs.setdefault("registry_type_name", "reflected")
        return super().real_add_to_registry(**kwargs)

    @classmethod
    def build(cls, schema: str | None = None, metadata: Any | None = None):
        del metadata
        return super().build(schema=schema)


__all__ = ["ReflectedModelMixin"]
