from __future__ import annotations

from typing import Any


class DumpMixin:
    def model_dump(self, *args: Any, **kwargs: Any):
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any):
        return super().model_dump_json(*args, **kwargs)


__all__ = ["DumpMixin"]
