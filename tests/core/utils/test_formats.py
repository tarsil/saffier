from __future__ import annotations

import datetime
import ipaddress
import uuid

import pytest

from saffier.core.utils.formats import (
    DateFormat,
    DateTimeFormat,
    EmailFormat,
    IPAddressFormat,
    TimeFormat,
    URLFormat,
    UUIDFormat,
)
from saffier.exceptions import ValidationError


def test_date_format_valid_and_invalid():
    fmt = DateFormat()
    assert fmt.check("2024-02-29") == datetime.date(2024, 2, 29)
    with pytest.raises(ValidationError):
        fmt.check("bad-date")


def test_time_format_valid_and_invalid():
    fmt = TimeFormat()
    assert fmt.check("10:20:30.123") == datetime.time(10, 20, 30, 123000)
    with pytest.raises(ValidationError):
        fmt.check("25:00:00")


def test_datetime_format_with_timezone():
    fmt = DateTimeFormat()
    value = fmt.check("2024-05-01T10:20:30+02:00")
    assert isinstance(value, datetime.datetime)
    assert value.tzinfo is not None
    assert value.utcoffset() == datetime.timedelta(hours=2)

    zulu = fmt.check("2024-05-01T10:20:30Z")
    assert zulu.tzinfo == datetime.timezone.utc

    with pytest.raises(ValidationError):
        fmt.check("nope")


def test_uuid_email_ip_and_url_formats():
    uuid_fmt = UUIDFormat()
    token = str(uuid.uuid4())
    parsed = uuid_fmt.check(token)
    assert isinstance(parsed, uuid.UUID)
    assert uuid_fmt.is_native_type(parsed) is True
    with pytest.raises(ValidationError):
        uuid_fmt.check("invalid")

    email_fmt = EmailFormat()
    assert email_fmt.check("alice@example.com") == "alice@example.com"
    with pytest.raises(ValidationError):
        email_fmt.check("bad")

    ip_fmt = IPAddressFormat()
    ip_value = ip_fmt.check("127.0.0.1")
    assert isinstance(ip_value, ipaddress.IPv4Address)
    with pytest.raises(ValidationError):
        ip_fmt.check("999.999.999.999")

    url_fmt = URLFormat()
    assert url_fmt.check("https://example.com/path") == "https://example.com/path"
    with pytest.raises(ValidationError):
        url_fmt.check("example.com")
