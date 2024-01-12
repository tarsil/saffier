import os

import pytest

os.environ.setdefault("SETTINGS_MODULE", "tests.settings.TestSettings")


@pytest.fixture(scope="module")
def anyio_backend():
    return ("asyncio", {"debug": True})
