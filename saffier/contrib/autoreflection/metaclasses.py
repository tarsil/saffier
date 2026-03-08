from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from saffier.core.db.models.metaclasses import BaseModelReflectMeta, MetaInfo

if TYPE_CHECKING:
    from sqlalchemy import Table


class AutoReflectionMetaInfo(MetaInfo):
    __slots__ = (
        "include_pattern",
        "exclude_pattern",
        "template",
        "databases",
        "schemes",
        "is_pattern_model",
    )
    include_pattern: re.Pattern[str]
    exclude_pattern: re.Pattern[str] | None
    template: Callable[[Table], str]
    databases: frozenset[str | None]
    schemes: frozenset[str | None]
    is_pattern_model: bool

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        self.include_pattern = getattr(meta, "include_pattern", None)
        self.exclude_pattern = getattr(meta, "exclude_pattern", None)
        self.template = getattr(meta, "template", None)
        self.databases = getattr(meta, "databases", (None,))  # type: ignore[assignment]
        self.schemes = getattr(meta, "schemes", (None,))  # type: ignore[assignment]
        self.is_pattern_model = bool(getattr(meta, "is_pattern_model", True))
        super().__init__(meta, **kwargs)
        self._normalize()

    def _normalize(self) -> None:
        template: Any = self.template
        if template is None:
            template = "{modelname}{tablename}"
        if isinstance(template, str):

            def render(
                table: Table, template: str = template, meta: AutoReflectionMetaInfo = self
            ) -> str:
                model = meta.model.__name__ if meta.model is not None else "Model"
                return template.format(
                    tablename=table.name,
                    tablekey=table.key,
                    modelname=model,
                )

            self.template = render

        include_pattern: Any = self.include_pattern
        if not include_pattern:
            include_pattern = ".*"
        if isinstance(include_pattern, str):
            include_pattern = re.compile(include_pattern)
        self.include_pattern = include_pattern

        exclude_pattern: Any = self.exclude_pattern
        if not exclude_pattern:
            exclude_pattern = None
        elif isinstance(exclude_pattern, str):
            exclude_pattern = re.compile(exclude_pattern)
        self.exclude_pattern = exclude_pattern

        self.databases = frozenset(cast(Any, self.databases))
        self.schemes = frozenset(
            cast(Any, (schema if schema else None for schema in self.schemes))
        )


class AutoReflectionMeta(BaseModelReflectMeta):
    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        meta_info_class: type[AutoReflectionMetaInfo] = AutoReflectionMetaInfo,
        **kwargs: Any,
    ) -> type:
        meta_class = attrs.get("Meta", type("Meta", (), {}))
        if not hasattr(meta_class, "abstract"):
            meta_class.abstract = True
        attrs["Meta"] = meta_class

        new_model = cast(
            type,
            super().__new__(
                cls,
                name,
                bases,
                attrs,
                meta_info_class=meta_info_class,
                **kwargs,
            ),
        )

        if name == "AutoReflectModel":
            return new_model

        meta = cast(AutoReflectionMetaInfo, new_model.meta)
        if meta.is_pattern_model and meta.registry is not None:
            meta.registry.pattern_models[new_model.__name__] = new_model

        return new_model
