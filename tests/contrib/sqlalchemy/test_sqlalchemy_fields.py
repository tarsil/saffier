from __future__ import annotations

import ipaddress
import uuid
from types import SimpleNamespace

import sqlalchemy

from saffier.contrib.sqlalchemy.fields import GUID, IPAddress, List
from saffier.contrib.sqlalchemy.types import SubList


def test_guid_field_processing():
    guid = GUID()
    postgres = SimpleNamespace(name="postgres", type_descriptor=lambda value: value)
    sqlite = SimpleNamespace(name="sqlite", type_descriptor=lambda value: value)

    assert isinstance(guid.load_dialect_impl(postgres), sqlalchemy.dialects.postgresql.UUID)
    assert isinstance(guid.load_dialect_impl(sqlite), sqlalchemy.CHAR)

    uid = uuid.uuid4()
    assert guid.process_bind_param(uid, sqlite) == uid.hex
    assert guid.process_bind_param(uid, postgres) == str(uid)
    assert guid.process_bind_param(None, postgres) is None
    assert guid.process_result_value(str(uid), postgres) == uid


def test_ip_address_field_processing():
    field = IPAddress()
    postgres = SimpleNamespace(name="postgres", type_descriptor=lambda value: value)
    sqlite = SimpleNamespace(name="sqlite", type_descriptor=lambda value: value)

    assert isinstance(field.load_dialect_impl(postgres), sqlalchemy.dialects.postgresql.INET)
    assert isinstance(field.load_dialect_impl(sqlite), sqlalchemy.CHAR)

    assert field.process_bind_param(ipaddress.ip_address("127.0.0.1"), postgres) == "127.0.0.1"
    assert field.process_result_value("127.0.0.1", postgres) == ipaddress.ip_address("127.0.0.1")
    assert field.process_result_value(None, postgres) is None


def test_list_field_processing(monkeypatch):
    field = List(delimiter=";")
    postgres = SimpleNamespace(name="postgres", type_descriptor=lambda value: value)
    sqlite = SimpleNamespace(name="sqlite", type_descriptor=lambda value: value)

    assert isinstance(field.load_dialect_impl(postgres), sqlalchemy.dialects.postgresql.VARCHAR)
    assert isinstance(field.load_dialect_impl(sqlite), sqlalchemy.CHAR)

    monkeypatch.setattr("saffier.contrib.sqlalchemy.fields.loads", lambda value: ["a", "b"])
    assert field.process_bind_param('["a","b"]', postgres) == ["a", "b"]

    assert field.process_result_value(["a"], postgres) == ["a"]
    empty = field.process_result_value(None, postgres)
    assert isinstance(empty, SubList)
    assert str(SubList(";", ["a", "b"])) == "a;b"
