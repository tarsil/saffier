import os
import shutil
from contextlib import suppress

import pytest

from tests.cli.utils import run_cmd

BASE_PATH = os.path.split(os.path.abspath(__file__))[0]


@pytest.fixture(autouse=True)
def cleanup_folders():
    os.chdir(BASE_PATH)
    with suppress(OSError):
        shutil.rmtree("migrations")
    with suppress(OSError):
        shutil.rmtree("migrations2")
    yield
    with suppress(OSError):
        shutil.rmtree("migrations")
    with suppress(OSError):
        shutil.rmtree("migrations2")


def test_list_templates_includes_builtin_variants():
    output, _, status = run_cmd("tests.cli.main:app", "saffier list-templates")
    text = output.decode("utf-8")

    assert status == 0
    assert "default -" in text
    assert "plain -" in text
    assert "url -" in text
    assert "sequencial -" in text


@pytest.mark.parametrize("template", ["default", "plain", "url", "sequencial"])
def test_init_builtin_templates(template):
    output, error, status = run_cmd(
        "tests.cli.main:app", f"saffier init -d migrations2 -t {template}"
    )
    assert status == 0, output.decode("utf-8") + error.decode("utf-8")

    assert os.path.isfile("migrations2/README")
    assert os.path.isfile("migrations2/alembic.ini")
    assert os.path.isfile("migrations2/env.py")
    assert os.path.isfile("migrations2/script.py.mako")
    assert "settings.alembic_ctx_kwargs" in open("migrations2/env.py").read()

    if template == "sequencial":
        assert os.path.isfile("migrations2/generator.py")


def test_init_without_app_uses_settings_defaults():
    output, error, status = run_cmd(None, "saffier init -d migrations2 -t plain", is_app=False)
    assert status == 0, output.decode("utf-8") + error.decode("utf-8")
    assert os.path.isfile("migrations2/env.py")
