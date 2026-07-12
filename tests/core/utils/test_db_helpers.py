import warnings

import pytest

import saffier
from saffier.core.utils.db import (
    CHECK_DB_CONNECTION_SILENCED,
    FORCE_FIELDS_NULLABLE,
    check_db_connection,
    force_fields_nullable_as_list_string,
    hash_names,
    hash_tablekey,
    with_force_fields_nullable,
)
from saffier.exceptions import DatabaseNotConnectedWarning


class _FakeDatabase:
    def __init__(self, *, is_connected: bool, force_rollback: bool = False) -> None:
        self.is_connected = is_connected
        self.force_rollback = force_rollback


def test_hash_tablekey_uses_prefix_and_passthrough() -> None:
    assert hash_tablekey(tablekey="users", prefix="") == "users"
    assert hash_tablekey(tablekey="users", prefix="groups").startswith("_join")


def test_hash_names_is_stable() -> None:
    first = hash_names(["b", "a"], inner_prefix="fields", outer_prefix="idx_")
    second = hash_names(["a", "b"], inner_prefix="fields", outer_prefix="idx_")
    assert first == second
    assert first.startswith("idx_")


def test_force_fields_nullable_string_formats_context_items() -> None:
    token = FORCE_FIELDS_NULLABLE.set((("public", "users.name"), ("tenant", "groups.slug")))
    try:
        result = force_fields_nullable_as_list_string()
    finally:
        FORCE_FIELDS_NULLABLE.reset(token)

    assert result == '[("public", "users.name"), ("tenant", "groups.slug")]'


def test_with_force_fields_nullable_scopes_and_validates_selectors() -> None:
    """Verify scoped forced-nullable selector parsing and cleanup.

    The migration CLI passes raw strings into the context manager, while
    generated templates consume normalized tuple values. This test proves both
    explicit model selectors and wildcard selectors are normalized during the
    context and that the previous empty state is restored afterwards.
    """
    with with_force_fields_nullable(("User:name", ":slug")):
        assert force_fields_nullable_as_list_string() == '[("", "slug"), ("User", "name")]'

    assert force_fields_nullable_as_list_string() == "[]"

    with pytest.raises(ValueError, match="model:field"), with_force_fields_nullable(("broken",)):
        pass


def test_force_fields_nullable_changes_generated_column_nullability() -> None:
    """Verify field metadata honors the migration-only nullable override.

    Saffier models keep their declared ``null=False`` semantics, but Alembic
    autogeneration reads SQLAlchemy columns from model metadata. This test
    confirms selected fields render nullable only while the migration context is
    active, including wildcard selectors that apply by field name.
    """
    test_registry = saffier.Registry(database="sqlite+aiosqlite:///force-nullable.db")

    class ForceNullableUser(saffier.Model):
        id = saffier.IntegerField(primary_key=True)
        name = saffier.CharField(max_length=50)

        class Meta:
            registry = test_registry

    assert ForceNullableUser.fields["name"].get_column("name").nullable is False

    with with_force_fields_nullable((("ForceNullableUser", "name"),)):
        assert ForceNullableUser.fields["name"].get_column("name").nullable is True

    with with_force_fields_nullable((":name",)):
        assert ForceNullableUser.fields["name"].get_column("name").nullable is True


def test_check_db_connection_warns_and_can_be_silenced() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_db_connection(_FakeDatabase(is_connected=False))

    assert caught
    assert issubclass(caught[0].category, DatabaseNotConnectedWarning)

    token = CHECK_DB_CONNECTION_SILENCED.set(True)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            check_db_connection(_FakeDatabase(is_connected=False))
        assert caught == []
    finally:
        CHECK_DB_CONNECTION_SILENCED.reset(token)


def test_check_db_connection_raises_for_force_rollback() -> None:
    with pytest.raises(RuntimeError, match="db is not connected"):
        check_db_connection(_FakeDatabase(is_connected=False, force_rollback=True))
