from saffier.testing import DatabaseTestClient
from saffier.testing.client import DatabaseTestClient as DatabaseTestClientAlias
from saffier.testing.exceptions import ExcludeValue, InvalidModelError


def test_testing_exports():
    assert DatabaseTestClient is DatabaseTestClientAlias
    assert issubclass(InvalidModelError, Exception)
    assert issubclass(ExcludeValue, Exception)
