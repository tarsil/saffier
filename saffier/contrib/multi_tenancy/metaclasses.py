from typing import Any

from saffier.core.db import fields as saffier_fields
from saffier.core.db.models.metaclasses import (
    BaseModelMeta,
    MetaInfo,
    _check_model_inherited_registry,
    get_model_meta_attr,
)


def _check_model_inherited_tenancy(bases: tuple[type, ...]) -> bool | None:
    """
    When a registry is missing from the Meta class, it should look up for the bases
    and obtain the first found registry.

    If not found, then a ImproperlyConfigured exception is raised.
    """
    is_tenant: bool | None = None

    for base in bases:
        meta: MetaInfo = getattr(base, "meta", None)  # type: ignore
        if not meta:
            continue

        meta_tenant: bool | None = getattr(meta, "is_tenant", None)
        if meta_tenant is not None and meta_tenant is not False:
            is_tenant = meta_tenant
            break

    return is_tenant


class TenantMeta(MetaInfo):
    __slots__ = ("is_tenant", "register_default")

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        super().__init__(meta, **kwargs)
        self.is_tenant: bool = getattr(meta, "is_tenant", False)
        self.register_default: bool | None = getattr(meta, "register_default", None)

    def set_tenant(self, is_tenant: bool) -> None:
        self.is_tenant = is_tenant


class BaseTenantMeta(BaseModelMeta):
    """
    The metaclass for the base tenant used by the Saffier contrib mixin.

    This should only be used by the contrib or if you decided to use
    your own tenant model using the `is_tenant` inside the `Meta` object.
    """

    def __new__(cls, name: str, bases: tuple[type, ...], attrs: Any) -> Any:
        from saffier.contrib.contenttypes.fields import ContentTypeField

        meta_class: object = attrs.get("Meta", type("Meta", (), {}))
        new_model = super().__new__(cls, name, bases, attrs)
        meta: TenantMeta = TenantMeta(new_model.meta)

        if hasattr(meta_class, "is_tenant"):
            meta.set_tenant(meta_class.is_tenant)

        # Handle the registry of models
        if getattr(meta, "registry", None) is None:
            if hasattr(new_model, "__db_model__") and new_model.__db_model__:
                meta.registry = _check_model_inherited_registry(bases)
            else:
                return new_model

        registry = meta.registry
        new_model.meta = meta

        # Check if is tenant
        is_tenant = _check_model_inherited_tenancy(bases)
        if is_tenant:
            new_model.meta.is_tenant = is_tenant

        register_default = get_model_meta_attr("register_default", bases, meta_class)
        if hasattr(meta_class, "register_default"):
            register_default = meta_class.register_default
        new_model.meta.register_default = register_default

        if new_model.meta.is_tenant:
            for field in new_model.fields.values():
                if not isinstance(field, ContentTypeField):
                    continue
                field.no_constraint = True
                registry_content_type = getattr(registry, "content_type", None)
                if registry_content_type is not None:
                    registry_content_type.__require_model_based_deletion__ = True
            if registry and hasattr(registry, "_clear_model_table_cache"):
                registry._clear_model_table_cache(new_model)

        if registry:
            try:
                if meta.is_tenant and not meta.abstract:
                    if meta.register_default is False:
                        registry.models.pop(new_model.__name__, None)
                    registry.tenant_models[new_model.__name__] = new_model
                    for value in new_model.fields.values():
                        if not isinstance(value, saffier_fields.ManyToManyField):
                            continue
                        through_model = getattr(value, "through", None)
                        if not isinstance(through_model, type):
                            continue
                        registry.tenant_models[through_model.__name__] = through_model
                        if meta.register_default is False:
                            registry.models.pop(through_model.__name__, None)
            except KeyError:
                ...  # pragma: no cover
        return new_model
