import asyncio
import os
import shutil

import pytest
import sqlalchemy
from esmerald import Esmerald
from sqlalchemy.ext.asyncio import create_async_engine

from tests.cli.utils import run_cmd
from tests.settings import DATABASE_URL

app = Esmerald(routes=[])


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
    from saffier.cli import alembic_version

    assert len(alembic_version) == 3

    for v in alembic_version:
        assert isinstance(v, int)


async def cleanup_prepare_db():
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("DROP DATABASE test_saffier"))
    except Exception:
        pass
    async with engine.connect() as conn:
        await conn.execute(sqlalchemy.text("CREATE DATABASE test_saffier"))


def test_migrate_upgrade(create_folders):
    asyncio.run(cleanup_prepare_db())
    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier init -t ./custom")
    assert ss == 0

    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier makemigrations")
    assert ss == 0

    (o, e, ss) = run_cmd("tests.cli.main:app", "saffier migrate")
    assert ss == 0

    with open("migrations/README") as f:
        assert f.readline().strip() == "Custom template"
    with open("migrations/alembic.ini") as f:
        assert f.readline().strip() == "# A generic, single database configuration"
    with open("migrations/env.py") as f:
        assert f.readline().strip() == "# Custom env template"
    with open("migrations/script.py.mako") as f:
        assert f.readline().strip() == "# Custom mako template"
