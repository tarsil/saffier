from __future__ import annotations

from typing import Any

from saffier.core.db.models.metaclasses import BaseModelMeta


class ContentTypeMeta(BaseModelMeta):
    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        meta_class = attrs.get("Meta")
        if meta_class is None:
            attrs["Meta"] = type("Meta", (), {"registry": False})
            meta_class = attrs["Meta"]
        elif getattr(meta_class, "registry", None) is None:
            meta_class.registry = False
        if getattr(meta_class, "registry", None) is False:
            attrs.setdefault("__skip_registry__", True)
        new_model = super().__new__(cls, name, bases, attrs, **kwargs)
        if getattr(new_model, "no_constraint", False):
            new_model.__require_model_based_deletion__ = True
        return new_model
