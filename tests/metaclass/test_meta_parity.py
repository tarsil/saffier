import pytest
import sqlalchemy

import saffier
from saffier import Manager
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def build_registry() -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL))


def test_meta_fields_is_mapping_and_alias() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert isinstance(User.meta.fields, dict)
    assert User.meta.fields is User.meta.fields_mapping
    assert "id" in User.meta.fields
    assert "name" in User.meta.fields
    assert User.meta.fields["name"] is User.fields["name"]


def test_meta_constraints_and_table_prefix_are_applied() -> None:
    registry_obj = build_registry()

    class Audit(saffier.Model):
        value = saffier.IntegerField()

        class Meta:
            registry = registry_obj
            table_prefix = "audit"
            constraints = [
                sqlalchemy.CheckConstraint("value >= 0", name="audit_value_non_negative")
            ]

    assert Audit.meta.tablename == "audit_audits"
    constraint_names = {constraint.name for constraint in Audit.table.constraints}
    assert "audit_value_non_negative" in constraint_names


def test_table_prefix_is_inherited_from_abstract_base() -> None:
    registry_obj = build_registry()

    class BaseRecord(saffier.Model):
        class Meta:
            abstract = True
            registry = registry_obj
            table_prefix = "tenant"

    class Product(BaseRecord):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert Product.meta.tablename == "tenant_products"


def test_constraints_type_validation() -> None:
    registry_obj = build_registry()

    with pytest.raises(
        ImproperlyConfigured,
        match="constraints must be a tuple or list. Got dict instead.",
    ):

        class Broken(saffier.Model):
            name = saffier.CharField(max_length=32)

            class Meta:
                registry = registry_obj
                constraints = {"name": "invalid"}


def test_pk_helpers_and_table_schema_cache() -> None:
    registry_obj = build_registry()

    class Item(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert tuple(Item.pknames) == ("id",)
    assert tuple(Item.pkcolumns) == ("id",)

    tenant_table_one = Item.table_schema("tenant_a")
    tenant_table_two = Item.table_schema("tenant_a")

    assert tenant_table_one is tenant_table_two
    assert Item._db_schemas["tenant_a"] is tenant_table_one
    assert Item.table_schema() is Item.table


def test_field_inherit_false_is_not_propagated() -> None:
    registry_obj = build_registry()

    class BaseEntity(saffier.Model):
        visible = saffier.CharField(max_length=100)
        hidden = saffier.CharField(max_length=100, inherit=False)

        class Meta:
            registry = registry_obj

    class ChildEntity(BaseEntity):
        description = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert "visible" in ChildEntity.fields
    assert "hidden" not in ChildEntity.fields


class ActiveManager(Manager):
    pass


def test_manager_inherit_false_is_not_propagated() -> None:
    registry_obj = build_registry()

    class BaseEntity(saffier.Model):
        active = ActiveManager()
        hidden = Manager(inherit=False)

        class Meta:
            registry = registry_obj

    class ChildEntity(BaseEntity):
        description = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert isinstance(BaseEntity.active, ActiveManager)
    assert isinstance(ChildEntity.active, ActiveManager)
    assert ChildEntity.hidden is None
