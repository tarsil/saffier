from __future__ import annotations

from dataclasses import dataclass

import pytest

from saffier.conf import (
    ENVIRONMENT_VARIABLE,
    configure_settings,
    override_settings,
    reload_settings,
)
from saffier.conf.enums import EnvironmentType
from saffier.conf.module_import import import_string


def test_import_string_errors_and_success():
    with pytest.raises(ImportError):
        import_string("invalid")
    with pytest.raises(ImportError):
        import_string("saffier.conf.module_import.NotThere")

    loaded = import_string("saffier.conf.global_settings.SaffierSettings")
    assert loaded.__name__ == "SaffierSettings"
    colon_loaded = import_string("saffier.conf.global_settings:SaffierSettings")
    assert colon_loaded.__name__ == "SaffierSettings"


def test_configure_reload_and_override(monkeypatch: pytest.MonkeyPatch):
    @dataclass
    class LocalSettings:
        value: str = "base"
        lower: str = "ok"

        def dict(self):
            return {"value": self.value, "lower": self.lower}

    resolved = configure_settings(LocalSettings, value="configured")
    assert resolved.value == "configured"

    with override_settings(value="temp") as scoped:
        assert scoped.value == "temp"

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "saffier.conf.global_settings.SaffierSettings")
    reloaded = reload_settings()
    assert hasattr(reloaded, "default_related_lookup_field")


def test_global_helpers_and_environment_enum(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "saffier.conf.global_settings.SaffierSettings")
    configured = configure_settings()
    assert hasattr(configured, "many_to_many_relation")

    with override_settings(default_related_lookup_field="uuid") as scoped:
        assert scoped.default_related_lookup_field == "uuid"

    reset = reload_settings()
    assert reset.default_related_lookup_field == "id"
    assert EnvironmentType.DEVELOPMENT.value == "development"
