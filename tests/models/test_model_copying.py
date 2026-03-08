from __future__ import annotations

import saffier
from saffier.core.db.models.managers import Manager
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def build_registry(**kwargs: object) -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL), **kwargs)


def test_copy_model_returns_detached_concrete_model() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    copied = User.copy_saffier_model()

    assert copied is not User
    assert copied.meta.registry is False
    assert copied.meta.tablename == User.meta.tablename
    assert copied.fields["name"].name == "name"


def test_add_to_registry_preserves_original_model_registry() -> None:
    registry_obj = build_registry()
    target_registry = build_registry(schema="tenant_copy")

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    copied = User.copy_saffier_model()
    added = copied.add_to_registry(target_registry)

    assert added is target_registry.get_model("User")
    assert added.meta.registry is target_registry
    assert User.meta.registry is registry_obj
    assert target_registry.get_model("User") is not User


def test_add_to_registry_resolves_forward_foreign_keys_lazily() -> None:
    source_registry = build_registry()
    target_registry = build_registry(schema="tenant_copy")

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = source_registry

    class Profile(saffier.Model):
        user = saffier.ForeignKey(User)
        display_name = saffier.CharField(max_length=100)

        class Meta:
            registry = source_registry

    detached_profile = Profile.copy_saffier_model()
    copied_profile = detached_profile.add_to_registry(target_registry)

    assert copied_profile.fields["user"].to == "User"
    assert "profiles_set" not in copied_profile.meta.related_fields

    copied_user = User.copy_saffier_model(registry=target_registry)

    assert copied_profile.fields["user"].target is copied_user
    assert hasattr(copied_user, "profiles_set")
    assert copied_user.meta.related_names_mapping["profiles_set"] == "user"


def test_add_to_registry_on_conflict_keep_and_replace() -> None:
    source_registry = build_registry()
    target_registry = build_registry(schema="tenant_copy")

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = source_registry

    first = User.copy_saffier_model(registry=target_registry)
    kept = User.copy_saffier_model().add_to_registry(target_registry, on_conflict="keep")
    replaced = User.copy_saffier_model().add_to_registry(target_registry, on_conflict="replace")

    assert kept is first
    assert replaced is target_registry.get_model("User")
    assert replaced is not first


def test_related_name_false_skips_reverse_relation_registration() -> None:
    registry_obj = build_registry()

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class AuditLog(saffier.Model):
        user = saffier.ForeignKey(User, related_name=False)
        event = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    assert AuditLog.fields["user"].related_name is False
    assert not hasattr(User, "auditlogs_set")
    assert "auditlogs_set" not in User.meta.related_fields


def test_manager_prefers_explicit_using_schema() -> None:
    registry_obj = build_registry(schema="public")

    class User(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    original_schema = User.__using_schema__
    try:
        User.__using_schema__ = "tenant_a"
        class_queryset = User.query.get_queryset()
        assert class_queryset.using_schema == "tenant_a"
        assert class_queryset.table.schema == "tenant_a"

        instance = User(id=1, name="Alice")
        instance.__using_schema__ = "tenant_b"
        instance_queryset = Manager(owner=User, instance=instance).get_queryset()
        assert instance_queryset.using_schema == "tenant_b"
        assert instance_queryset.table.schema == "tenant_b"
    finally:
        User.__using_schema__ = original_schema
