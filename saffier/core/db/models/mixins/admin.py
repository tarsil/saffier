from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from saffier.core import marshalls

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


class AdminMixin:
    """
    Model-level hooks used by Saffier's admin and schema helpers.

    The mixin keeps admin projection policy on the model class rather than in
    templates or controllers. Applications can override any hook to customize
    which fields appear in list, view, create, update, and schema-generation
    phases while the admin service continues to use normal Saffier marshalling
    and validation paths.
    """

    @classmethod
    def get_admin_marshall_config(
        cls: type[Model], *, phase: str, for_schema: bool
    ) -> dict[str, Any]:
        """
        Return the marshall configuration for one admin phase.

        Args:
            phase: Admin phase requesting a marshall. Common values are
                ``"list"``, ``"view"``, ``"create"``, and ``"update"``.
            for_schema: Whether the configuration is being requested for JSON
                schema generation rather than request validation or display.

        Returns:
            dict[str, Any]: Keyword arguments passed to
            ``marshalls.ConfigMarshall`` when building the phase-specific
            marshall class.
        """
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
        """
        Build the marshall class used by Saffier admin for one phase.

        Args:
            phase: Admin phase requesting a projection/validation class.
            for_schema: Whether the class will be used for JSON schema
                generation. Applications can use this flag to expose schema-only
                fields without accepting them during writes.

        Returns:
            type[marshalls.Marshall]: Dynamically named marshall class bound to
            the model and phase-specific configuration.
        """
        config = cls.get_admin_marshall_config(phase=phase, for_schema=for_schema)
        if config.get("exclude") is not None and config.get("fields") == ["__all__"]:
            config = dict(config)
            config.pop("fields", None)

        class AdminMarshall(marshalls.Marshall):
            marshall_config = marshalls.ConfigMarshall(model=cls, **config)

        AdminMarshall.__name__ = f"{cls.__name__}{phase.title()}AdminMarshall"
        return AdminMarshall

    @classmethod
    def get_admin_marshall_for_save(
        cls: type[Model], instance: Model | None = None, /, **kwargs: Any
    ) -> marshalls.Marshall:
        """
        Build the marshall used to validate admin create and update payloads.

        Args:
            instance: Existing model instance for update operations. ``None``
                means the admin is creating a new row.
            **kwargs: Submitted field values after the admin service has parsed
                the request payload.

        Returns:
            marshalls.Marshall: Marshall instance ready to validate and expose
            values for persistence.
        """
        phase = "update" if instance is not None else "create"
        AdminMarshallClass = cls.get_admin_marshall_class(phase=phase, for_schema=False)
        return cast("marshalls.Marshall", AdminMarshallClass(instance, **kwargs))


__all__ = ["AdminMixin"]
