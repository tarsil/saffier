from __future__ import annotations

from typing import ClassVar, cast

import saffier

from .metaclasses import ContentTypeMeta


class ContentType(saffier.Model, metaclass=ContentTypeMeta):
    no_constraint: ClassVar[bool] = False

    class Meta:
        abstract = True

    name = saffier.CharField(max_length=100, default="", index=True)
    schema_name = saffier.CharField(max_length=63, null=True, index=True)
    collision_key = saffier.CharField(max_length=255, null=True, unique=True)

    async def get_instance(self) -> saffier.Model:
        reverse_name = f"reverse_{str(self.name).lower()}"
        return cast("saffier.Model", await getattr(self, reverse_name).get())
