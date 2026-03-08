from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from saffier.conf import (
    ENVIRONMENT_VARIABLE,
    BaseSettings,
    _monkay,
    add_settings_extension,
    evaluate_settings_once_ready,
    override_settings,
    reload_settings,
    settings,
    with_settings,
)


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "tests.settings.TestSettings")
    reload_settings()
    yield
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "tests.settings.TestSettings")
    reload_settings()


def _write_module(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content))


def test_base_settings_casts_environment_values(monkeypatch: pytest.MonkeyPatch):
    class LocalSettings(BaseSettings):
        integer_value: int = 1
        enabled: bool = False
        names: list[str] = []
        payload: dict[str, int] = {}

        @property
        def summary(self) -> str:
            return f"{self.integer_value}:{self.enabled}"

    monkeypatch.setenv("INTEGER_VALUE", "42")
    monkeypatch.setenv("ENABLED", "yes")
    monkeypatch.setenv("NAMES", "alice,bob")
    monkeypatch.setenv("PAYLOAD", '{"workers": 4}')

    configured = LocalSettings()

    assert configured.integer_value == 42
    assert configured.enabled is True
    assert configured.names == ["alice", "bob"]
    assert configured.payload == {"workers": 4}
    assert configured.dict(include_properties=True)["summary"] == "42:True"


def test_with_settings_temporarily_replaces_values():
    baseline = settings.tenant_model

    with with_settings(None, tenant_model="ScopedTenant") as scoped:
        assert scoped.tenant_model == "ScopedTenant"
        assert settings.tenant_model == "ScopedTenant"

    assert settings.tenant_model == baseline


def test_override_settings_supports_sync_decorator():
    @override_settings(default_related_lookup_field="uuid")
    def decorated() -> str:
        return settings.default_related_lookup_field

    assert decorated() == "uuid"
    assert settings.default_related_lookup_field == "id"


@pytest.mark.anyio
async def test_override_settings_supports_async_decorator():
    @override_settings(default_related_lookup_field="slug")
    async def decorated() -> str:
        return settings.default_related_lookup_field

    assert await decorated() == "slug"
    assert settings.default_related_lookup_field == "id"


def test_evaluate_settings_runs_preloads_and_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.syspath_prepend(str(tmp_path))

    _write_module(
        tmp_path / "runtime_preload.py",
        """
        import saffier


        class App:
            pass


        app = App()
        saffier.monkay.set_instance(
            saffier.Instance(registry=object(), app=app, path="runtime_preload:app"),
            apply_extensions=False,
        )
        """,
    )
    _write_module(
        tmp_path / "runtime_extension.py",
        """
        calls = []


        class Extension:
            name = "runtime-extension"

            def apply(self, monkay_instance):
                calls.append(
                    (
                        monkay_instance.settings.default_related_lookup_field,
                        monkay_instance.instance.path,
                    )
                )
                monkay_instance.settings.default_related_lookup_field = "slug"
        """,
    )
    _write_module(
        tmp_path / "runtime_settings.py",
        """
        from runtime_extension import Extension
        from saffier.conf.global_settings import SaffierSettings


        class RuntimeSettings(SaffierSettings):
            preloads = ("runtime_preload",)
            extensions = (Extension,)
        """,
    )

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "runtime_settings.RuntimeSettings")
    reload_settings()

    configured = evaluate_settings_once_ready()

    assert configured.default_related_lookup_field == "slug"
    assert _monkay.instance.path == "runtime_preload:app"

    from runtime_extension import calls

    assert calls == [("id", "runtime_preload:app")]


def test_add_settings_extension_registers_runtime_extension():
    class RuntimeExtension:
        name = "dynamic-test-extension"

        def apply(self, monkay_instance) -> None:
            monkay_instance.settings.default_related_lookup_field = "dynamic"

    with override_settings(default_related_lookup_field="id"):
        add_settings_extension(RuntimeExtension, on_conflict="replace")
        _monkay.set_instance(type("Instance", (), {"app": object(), "path": "tests:app"})())
        _monkay.apply_extensions()
        assert settings.default_related_lookup_field == "dynamic"
