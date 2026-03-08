from __future__ import annotations

from typing import Any, ClassVar

import saffier

from .managers import PermissionManager


class BasePermission(saffier.Model):
    users_field_group: ClassVar[str] = "users"

    name = saffier.CharField(max_length=100, null=False)
    description = saffier.ComputedField(
        getter="get_description",
        setter="set_description",
        fallback_getter=lambda field, instance, owner: instance.name,
        null=True,
    )

    query: ClassVar[saffier.Manager] = PermissionManager()

    class Meta:
        abstract = True

    @classmethod
    def get_description(cls, field: Any, instance: Any, owner: Any = None) -> str:
        return str(instance.name)

    @classmethod
    def set_description(cls, field: Any, instance: Any, value: Any, owner: Any = None) -> None:
        instance.__dict__["description"] = value
