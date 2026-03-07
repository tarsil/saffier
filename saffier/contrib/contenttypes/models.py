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
        queryset = getattr(self, reverse_name)
        if self.schema_name is not None:
            queryset = queryset.using(schema=self.schema_name)
        return cast("saffier.Model", await queryset.get())

    async def delete(self) -> int:
        row_count = await super().delete()

        reverse_name = f"reverse_{str(self.name).lower()}"
        try:
            related_field = getattr(self, reverse_name)
        except AttributeError:
            return row_count

        fk_field_name = related_field.get_foreign_key_field_name()
        if not fk_field_name:
            return row_count

        foreign_key = related_field.related_from.fields.get(fk_field_name)
        if foreign_key is None or not getattr(foreign_key, "remove_referenced", True):
            return row_count

        queryset = related_field
        if self.schema_name is not None:
            queryset = queryset.using(schema=self.schema_name)
        await queryset.raw_delete(
            use_models=getattr(foreign_key, "use_model_based_deletion", False)
        )
        return row_count
