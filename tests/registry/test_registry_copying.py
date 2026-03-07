from __future__ import annotations

import copy

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL


def build_registry(**kwargs: object) -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL), **kwargs)


def test_registry_copy_preserves_explicit_through_relationships() -> None:
    registry_obj = build_registry()

    class Product(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class Membership(saffier.Model):
        product = saffier.ForeignKey(Product, null=False, on_delete=saffier.CASCADE)

        class Meta:
            registry = registry_obj

    class Cart(saffier.Model):
        name = saffier.CharField(max_length=100)
        products = saffier.ManyToManyField(Product, through=Membership)

        class Meta:
            registry = registry_obj

    copied_registry = saffier.get_migration_prepared_registry(copy.copy(registry_obj))

    copied_product = copied_registry.get_model("Product")
    copied_membership = copied_registry.get_model("Membership")
    copied_cart = copied_registry.get_model("Cart")

    assert copied_cart.fields["products"].through is copied_membership
    assert copied_membership.fields["product"].target is copied_product
    assert copied_cart.relation_products.through is copied_membership


def test_registry_copy_rebuilds_auto_many_to_many_through_models() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class Group(saffier.Model):
        name = saffier.CharField(max_length=100)
        users = saffier.ManyToManyField(User)

        class Meta:
            registry = registry_obj

    original_through = Group.fields["users"].through

    copied_registry = saffier.get_migration_prepared_registry(copy.copy(registry_obj))
    copied_user = copied_registry.get_model("User")
    copied_group = copied_registry.get_model("Group")
    copied_through = copied_group.fields["users"].through

    assert copied_through is not None
    assert copied_through is not original_through
    assert copied_through.meta.registry is copied_registry
    assert copied_through.fields["group"].target is copied_group
    assert copied_through.fields["user"].target is copied_user


def test_metadata_by_url_maps_to_per_database_metadata() -> None:
    registry = build_registry(extra={"another": Database(url=DATABASE_ALTERNATIVE_URL)})

    assert registry.metadata_by_url[str(registry.database.url)] is registry.metadata_by_name[None]
    assert (
        registry.metadata_by_url[str(registry.extra["another"].url)]
        is registry.metadata_by_name["another"]
    )
    assert registry.metadata_by_url.get_name(str(registry.extra["another"].url)) == "another"
