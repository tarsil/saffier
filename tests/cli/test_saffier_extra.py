from esmerald import Esmerald

from saffier import Registry
from saffier.cli.constants import SAFFIER_DB, SAFFIER_EXTRA
from tests.cli.main import app as main_app
from tests.cli.main_extra import app as extra_app


def test_has_saffier_extra():
    assert hasattr(extra_app, SAFFIER_EXTRA)


def test_extra_esmerald():
    extra = getattr(extra_app, SAFFIER_EXTRA)["extra"]
    assert isinstance(extra.app, Esmerald)


def test_has_saffier_migration():
    assert hasattr(main_app, SAFFIER_DB)


def test_migration_registry():
    extra = getattr(main_app, SAFFIER_DB)["migrate"]
    assert isinstance(extra.registry, Registry)
