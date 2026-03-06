import pytest

from saffier.core.db.datastructures import UniqueConstraint


def test_raises_value_error_on_wrong_unique_constraint_max_length():
    with pytest.raises(ValueError, match="max length"):
        UniqueConstraint(fields=["name"], name="x" * 64)


def test_raises_value_error_on_wrong_type_passed_fields():
    with pytest.raises(ValueError, match="list or a tuple"):
        UniqueConstraint(fields=2)  # type: ignore[arg-type]


def test_raises_value_error_on_wrong_type_inside_fields():
    with pytest.raises(ValueError, match="contain only strings"):
        UniqueConstraint(fields=["name", 2])  # type: ignore[list-item]


def test_unique_constraint_converts_tuple_fields_to_list():
    constraint = UniqueConstraint(fields=("name", "email"))

    assert constraint.fields == ["name", "email"]
