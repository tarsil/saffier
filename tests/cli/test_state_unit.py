import pytest

from saffier.cli.env import MigrationEnv
from saffier.cli.state import (
    clear_migration_env,
    get_migration_app,
    get_migration_env,
    set_migration_env,
)
from saffier.conf import _monkay
from saffier.exceptions import CommandEnvironmentError


@pytest.fixture(autouse=True)
def clear_runtime_state():
    clear_migration_env()
    _monkay.set_instance(None)
    yield
    clear_migration_env()
    _monkay.set_instance(None)


def test_state_errors_when_missing():
    with pytest.raises(CommandEnvironmentError):
        get_migration_env()


def test_state_errors_when_app_missing():
    env = MigrationEnv(path="x", app=None)
    set_migration_env(env)
    with pytest.raises(CommandEnvironmentError):
        get_migration_app()


def test_state_returns_loaded_app():
    app = object()
    env = MigrationEnv(path="x", app=app)
    set_migration_env(env)
    assert get_migration_app() is app
