import pytest

from saffier.conf import configure_settings, override_settings, reload_settings, settings
from tests.settings import TestSettings as AppSettings


@pytest.fixture(autouse=True)
def reset_test_settings(monkeypatch):
    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "tests.settings.TestSettings")
    reload_settings()
    yield
    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "tests.settings.TestSettings")
    reload_settings()


def test_reload_settings_uses_environment_module(monkeypatch):
    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "saffier.conf.global_settings.SaffierSettings")
    configured = reload_settings()

    assert configured.__class__.__name__ == "SaffierSettings"
    assert settings.__class__.__name__ == "SaffierSettings"


def test_configure_settings_supports_class_and_instance():
    configured = configure_settings(
        AppSettings, tenant_model="TenantOne", auth_user_model="UserOne"
    )
    assert configured.tenant_model == "TenantOne"
    assert settings.tenant_model == "TenantOne"

    configured = configure_settings(
        AppSettings(tenant_model="TenantTwo", auth_user_model="UserTwo")
    )
    assert configured.tenant_model == "TenantTwo"
    assert settings.tenant_model == "TenantTwo"


def test_override_settings_context_manager_restores_values():
    baseline_tenant = settings.tenant_model

    with override_settings(tenant_model="TemporaryTenant"):
        assert settings.tenant_model == "TemporaryTenant"

    assert settings.tenant_model == baseline_tenant
