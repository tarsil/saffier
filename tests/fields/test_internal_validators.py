from __future__ import annotations

import datetime
import decimal
import uuid

import pytest

from saffier.core.db.fields import _internal as internal
from saffier.exceptions import ValidationError


def test_string_validator_branches():
    field = internal.String(blank=True, trim_whitespace=True, min_length=2, max_length=5)
    assert field.check("  abc  ") == "abc"
    assert field.check(None) == ""

    required = internal.String(blank=False, null=False)
    with pytest.raises(ValidationError):
        required.check(None)

    patterned = internal.String(pattern=r"^a+$")
    assert patterned.check("aaa") == "aaa"
    with pytest.raises(ValidationError):
        patterned.check("bbb")

    email = internal.String(format="email")
    assert email.check("alice@example.com") == "alice@example.com"


def test_number_boolean_duration_and_binary():
    number = internal.Number(minimum=1, maximum=5, multiple_of=1)
    assert number.check(3) == 3
    with pytest.raises(ValidationError):
        number.check(0)

    integer = internal.Integer()
    with pytest.raises(ValidationError):
        integer.check(1.5)

    precise = internal.Float(precision="0.01")
    assert precise.check(1.234) == 1.23

    decimal_field = internal.Decimal()
    assert decimal_field.check("2.3") == decimal.Decimal("2.3")

    boolean = internal.Boolean()
    assert boolean.check("on") is True
    assert boolean.check("off") is False
    with pytest.raises(ValidationError):
        internal.Boolean(coerce_types=False).check("true")

    duration = internal.Duration()
    assert duration.check(5) == datetime.timedelta(seconds=5)
    assert duration.check("10") == datetime.timedelta(seconds=10)
    with pytest.raises(ValidationError):
        duration.check(object())

    binary = internal.Binary(max_length=4)
    assert binary.check("ab") == b"ab"
    assert binary.check(bytearray(b"ab")) == b"ab"
    with pytest.raises(ValidationError):
        binary.check("toolong")


def test_choice_union_const_and_specialized_strings():
    choice = internal.Choice(choices=["a", ("b", "B")], null=True)
    assert choice.check("a") == "a"
    assert choice.check("") is None
    with pytest.raises(ValidationError):
        choice.check("x")

    union = internal.Union(any_of=[internal.Integer(), internal.String(min_length=3)])
    assert union.check(2) == 2
    assert union.check("abcd") == "abcd"
    with pytest.raises(ValidationError):
        union.check("a")

    const = internal.Const("x")
    assert const.check("x") == "x"
    with pytest.raises(ValidationError):
        const.check("y")
    with pytest.raises(ValidationError):
        internal.Const(None).check("x")

    assert isinstance(internal.UUID().check(str(uuid.uuid4())), uuid.UUID)
    assert internal.Email().check("bob@example.com") == "bob@example.com"
    assert internal.IPAddress().check("127.0.0.1").compressed == "127.0.0.1"
    assert internal.URL().check("https://example.com") == "https://example.com"
