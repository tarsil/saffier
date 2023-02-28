import os
import shlex
import shutil
import subprocess

import pytest

from esmerald import Esmerald

app = Esmerald(routes=[])


def run_cmd(app, cmd):
    os.environ["SAFFIER_DEFAULT_APP"] = app
    process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = process.communicate()
    print("\n$ " + cmd)
    print(stdout.decode("utf-8"))
    print(stderr.decode("utf-8"))
    return stdout, stderr, process.wait()


@pytest.fixture(scope="module")
def create_folders():
    os.chdir(os.path.split(os.path.abspath(__file__))[0])
    try:
        os.remove("app.db")
    except OSError:
        pass
    try:
        shutil.rmtree("migrations")
    except OSError:
        pass
    try:
        shutil.rmtree("temp_folder")
    except OSError:
        pass

    yield

    try:
        os.remove("app.db")
    except OSError:
        pass
    try:
        shutil.rmtree("migrations")
    except OSError:
        pass
    try:
        shutil.rmtree("temp_folder")
    except OSError:
        pass


def test_alembic_version():
    from saffier.migrations import alembic_version

    assert len(alembic_version) == 3

    for v in alembic_version:
        assert isinstance(v, int)


def test_migrate_upgrade(create_folders):
    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier-admin init -t ./custom")
    assert ss == 0

    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier-admin makemigrations")
    assert ss == 0

    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier-admin migrate")
    assert ss == 0

    with open("migrations/README", "rt") as f:
        assert f.readline().strip() == "Custom template"
    with open("migrations/alembic.ini", "rt") as f:
        assert f.readline().strip() == "# A generic, single database configuration"
    with open("migrations/env.py", "rt") as f:
        assert f.readline().strip() == "# Custom env template"
    with open("migrations/script.py.mako", "rt") as f:
        assert f.readline().strip() == "# Custom mako template"
