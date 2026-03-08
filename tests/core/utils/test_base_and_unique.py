import pytest

from saffier.core.utils.base import BaseError, Message, Position, ValidationResult
from saffier.core.utils.unique import Uniqueness
from saffier.exceptions import ValidationError


def test_position_and_message_repr_and_equality():
    pos = Position(line_no=1, column_no=2, char_index=3)
    same = Position(line_no=1, column_no=2, char_index=3)
    assert pos == same
    assert "line_no=1" in repr(pos)

    message = Message(text="boom", code="invalid", key="name", position=pos)
    assert message.index == ["name"]
    assert "position" in repr(message)
    assert hash(message) == hash(Message(text="boom", code="invalid", key="name", position=pos))


def test_base_error_mapping_prefix_and_str():
    err = BaseError(
        messages=[
            Message(text="required", code="required", index=["user", "name"]),
            Message(text="invalid", code="invalid", index=["user", "age"]),
        ]
    )
    assert dict(err) == {"user": {"name": "required", "age": "invalid"}}
    prefixed = err.messages(prefix="payload")
    assert prefixed[0].index[0] == "payload"
    assert str(err) == str({"user": {"name": "required", "age": "invalid"}})

    simple = BaseError(text="single", code="single")
    assert str(simple) == "single"
    assert "single" in repr(simple)
    assert str(ValidationError(text="single", code="single")) == "single"


def test_validation_result_behaviour():
    ok = ValidationResult(value=1)
    assert bool(ok) is True
    assert list(ok) == [1, None]
    assert "value=1" in repr(ok)

    error = ValidationResult(error=ValidationError(text="bad", code="bad"))
    assert bool(error) is False
    assert "error=" in repr(error)


def test_uniqueness_hashing_rules():
    uniq = Uniqueness()
    uniq.add(True)
    uniq.add(False)
    uniq.add(["a", {"b": 1}])

    assert True in uniq
    assert False in uniq
    assert ["a", {"b": 1}] in uniq

    with pytest.raises(AssertionError):
        uniq.make_hashable(object())
