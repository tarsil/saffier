from urllib.parse import quote

import saffier
from saffier.core.connection import DatabaseURL
from saffier.core.db.models import ModelRef, StrictModel
from saffier.testing import ModelFactoryContext
from saffier.testing.factory import ModelFactoryContext as FactoryModelFactoryContext


def test_database_url_is_exported_and_masks_passwords() -> None:
    url = DatabaseURL("postgresql://username:password@localhost/mydatabase")
    escaped = DatabaseURL(f"postgresql://username:{quote('[password')}@localhost/mydatabase")

    assert saffier.DatabaseURL is DatabaseURL
    assert repr(url) == "DatabaseURL('postgresql://username:***@localhost/mydatabase')"
    assert escaped.password == "[password"


def test_core_exports_cover_new_parity_surface() -> None:
    assert saffier.StrictModel is StrictModel
    assert saffier.ModelRef is ModelRef
    assert ModelFactoryContext is FactoryModelFactoryContext
