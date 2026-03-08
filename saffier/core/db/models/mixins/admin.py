from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from saffier.core import marshalls

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


class AdminMixin:
    @classmethod
    def get_admin_marshall_config(
        cls: type[Model], *, phase: str, for_schema: bool
    ) -> dict[str, Any]:
        del for_schema
        return {
            "fields": ["__all__"],
            "exclude_read_only": phase in {"create", "update"},
            "primary_key_read_only": phase != "create",
            "exclude_autoincrement": phase == "create",
        }

    @classmethod
    def get_admin_marshall_class(
        cls: type[Model], *, phase: str, for_schema: bool = False
    ) -> type[marshalls.Marshall]:
        config = cls.get_admin_marshall_config(phase=phase, for_schema=for_schema)

        class AdminMarshall(marshalls.Marshall):
            marshall_config = marshalls.ConfigMarshall(model=cls, **config)

        AdminMarshall.__name__ = f"{cls.__name__}{phase.title()}AdminMarshall"
        return AdminMarshall

    @classmethod
    def get_admin_marshall_for_save(
        cls: type[Model], instance: Model | None = None, /, **kwargs: Any
    ) -> marshalls.Marshall:
        phase = "update" if instance is not None else "create"
        AdminMarshallClass = cls.get_admin_marshall_class(phase=phase, for_schema=False)
        return cast("marshalls.Marshall", AdminMarshallClass(instance, **kwargs))


__all__ = ["AdminMixin"]
