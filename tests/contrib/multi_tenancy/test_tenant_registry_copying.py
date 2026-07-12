from __future__ import annotations

import copy

import saffier
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def build_registry(**kwargs: object) -> TenantRegistry:
    return TenantRegistry(database=Database(url=DATABASE_URL), **kwargs)


def test_tenant_registry_copy_preserves_tenant_model_mapping() -> None:
    registry_obj = build_registry()

    class Product(TenantModel):
        name = fields.CharField(max_length=100)

        class Meta:
            registry = registry_obj
            is_tenant = True

    copied = copy.copy(registry_obj)

    assert isinstance(copied, TenantRegistry)
    assert copied.tenant_models["Product"] is copied.get_model("Product")
    assert copied.get_model("Product") is not Product


def test_register_default_false_skips_default_registry() -> None:
    registry_obj = build_registry()

    class Product(TenantModel):
        name = fields.CharField(max_length=100)

        class Meta:
            registry = registry_obj
            is_tenant = True
            register_default = False

    assert "Product" not in registry_obj.models
    assert registry_obj.tenant_models["Product"] is Product


def test_copied_tenant_model_add_to_registry_updates_tenant_models() -> None:
    source_registry = build_registry()
    target_registry = build_registry(schema="tenant_copy")

    class Product(TenantModel):
        name = fields.CharField(max_length=100)

        class Meta:
            registry = source_registry
            is_tenant = True
            register_default = False

    added = Product.copy_saffier_model().add_to_registry(target_registry)

    assert target_registry.tenant_models["Product"] is added
    assert "Product" not in target_registry.models


def test_tenant_many_to_many_through_models_are_tenant_registered() -> None:
    registry_obj = build_registry()

    class Product(TenantModel):
        name = fields.CharField(max_length=100)

        class Meta:
            registry = registry_obj
            is_tenant = True
            register_default = False

    class Cart(TenantModel):
        products = saffier.ManyToMany(Product)

        class Meta:
            registry = registry_obj
            is_tenant = True
            register_default = False

    through_model = Cart.fields["products"].through

    assert through_model is not None
    assert registry_obj.tenant_models[through_model.__name__] is through_model
    assert through_model.__name__ not in registry_obj.models
