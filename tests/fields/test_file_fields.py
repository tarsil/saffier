import io
import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="saffier-file-fields-"))
storage = saffier.files.FileSystemStorage(location=MEDIA_ROOT, base_url="/media/")
database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


def generated_file_name(instance, file, name: str, direct_name: bool) -> str:
    """
    Build a deterministic storage path from the active model instance.

    The callback proves that Saffier forwards the model instance into
    `generate_name_fn` during persistence. The file and direct-name arguments
    remain part of the signature so applications can inspect uploaded content
    or distinguish caller-provided names from names discovered on file objects.
    """
    del file, direct_name
    prefix = instance.__class__.__name__.lower() if instance is not None else "missing"
    return f"{prefix}/{name}"


class Asset(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    file = saffier.FileField(null=True, storage=storage)
    image = saffier.ImageField(null=True, storage=storage, image_formats=None)
    generated = saffier.FileField(
        null=True,
        storage=storage,
        with_size=False,
        with_metadata=False,
        generate_name_fn=generated_file_name,
    )
    path_only = saffier.FileField(
        null=True,
        storage=storage,
        with_size=False,
        with_metadata=False,
    )

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()
    shutil.rmtree(MEDIA_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
async def rollback_connection():
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    for child in MEDIA_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    with database.force_rollback():
        async with database:
            yield


def make_png(width: int = 2, height: int = 3) -> bytes:
    """
    Build a tiny PNG payload for image-field metadata assertions.

    The helper uses Pillow in memory so the test does not rely on checked-in
    binary fixtures. Width and height are parameters because the assertions
    intentionally prove that metadata comes from the image content, not from a
    hardcoded filename convention.
    """
    stream = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(stream, format="PNG")
    return stream.getvalue()


async def test_file_field_saves_upload_and_hydrates_field_file():
    document = await Asset.query.create(
        file=saffier.files.ContentFile(b"hello world", name="docs/hello.txt")
    )

    assert isinstance(document.file, saffier.files.FieldFile)
    assert document.file.committed is True
    assert document.file.name == "docs/hello.txt"
    assert document.file.size == 11
    assert document.file.metadata["mime"] == "text/plain"
    assert storage.exists(document.file.name)

    loaded = await Asset.query.get(pk=document.pk)

    assert isinstance(loaded.file, saffier.files.FieldFile)
    assert loaded.file.name == document.file.name
    assert loaded.file.size == 11
    assert loaded.file.metadata == {"mime": "text/plain"}
    assert loaded.model_dump()["file"] == "docs/hello.txt"
    assert await Asset.query.exists(file=loaded.file)


async def test_file_field_updates_upload_and_keeps_path_queries_string_compatible():
    document = await Asset.query.create(
        file=saffier.files.ContentFile(b"first", name="docs/first.txt")
    )

    await document.update(file=saffier.files.ContentFile(b"second", name="docs/second.txt"))
    loaded = await Asset.query.get(pk=document.pk)

    assert loaded.file == "docs/second.txt"
    assert loaded.file.size == 6
    assert loaded.file.metadata["mime"] == "text/plain"
    assert storage.exists("docs/second.txt")
    assert await Asset.query.exists(file="docs/second.txt")


async def test_file_field_can_remain_a_single_path_column_when_metadata_is_disabled():
    document = await Asset.query.create(path_only="external/report.pdf")

    assert "path_only_size" not in Asset.fields
    assert "path_only_metadata" not in Asset.fields
    assert document.path_only == "external/report.pdf"
    assert document.model_dump()["path_only"] == "external/report.pdf"


async def test_file_field_name_generator_receives_active_instance():
    document = await Asset.query.create(
        generated=saffier.files.ContentFile(b"named", name="uploads/custom.txt")
    )

    assert document.generated.name == "asset/uploads/custom.txt"
    assert storage.exists("asset/uploads/custom.txt")


async def test_image_field_extracts_dimensions_and_tracks_approval_column():
    image = saffier.files.ContentFile(make_png(), name="images/pixel.png")

    document = await Asset.query.create(image=image)
    loaded = await Asset.query.get(pk=document.pk)

    assert isinstance(loaded.image, saffier.files.ImageFieldFile)
    assert loaded.image.approved is False
    assert loaded.image.metadata["mime"] == "image/png"
    assert loaded.image.metadata["format"] == "PNG"
    assert loaded.image.metadata["width"] == 2
    assert loaded.image.metadata["height"] == 3
    assert "image_approved" in Asset.fields
