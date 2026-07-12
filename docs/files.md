# Files and Storage

Saffier now exposes a Python-native file and storage subsystem under `saffier.files`.

The subsystem is independent of Pydantic and is used directly by Saffier's ORM-managed
`FileField` and `ImageField`.

## What it provides

- `File`: a lightweight wrapper around file-like objects and stored files.
- `ContentFile`: an in-memory binary file.
- `FileUpload`: a Python-native serialized upload payload using `name` and raw/base64 `content`.
- `FieldFile`: the field-bound file wrapper returned by ORM file fields.
- `ImageFieldFile`: an image-aware field wrapper with optional Pillow helpers.
- `Storage`: the base contract for custom storage backends.
- `FileSystemStorage`: a local filesystem backend with safe path handling.
- `StorageHandler` and `storages`: backend registry/loader helpers.

## Quick example

```python
import saffier

storage = saffier.files.FileSystemStorage(location="media", base_url="/media/")
name = storage.save(b"hello world", "docs/hello.txt")

stored = saffier.files.File(name=name, storage=storage)
with stored.open() as file:
    assert file.read() == b"hello world"

assert stored.url == "/media/docs/hello.txt"
```

## Serialized uploads

`FileUpload` is a plain Python object that accepts a filename and raw bytes or base64 text.
It is useful when accepting serialized payloads before converting them into a `ContentFile`.

```python
from saffier.files import FileUpload

upload = FileUpload.from_data(
    {
        "name": "avatar.png",
        "content": "aGVsbG8=",  # base64
    }
)

content = upload.to_file()
```

## ORM-managed file fields

`FileField` stores the final file name in the model table and returns a `FieldFile`
object on model instances. New `File` and `ContentFile` values are saved through the
configured storage backend when the model is created or updated.

```python
import saffier

storage = saffier.files.FileSystemStorage(location="media", base_url="/media/")


class Asset(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    file = saffier.FileField(null=True, storage=storage)


asset = await Asset.query.create(
    file=saffier.files.ContentFile(b"hello", name="docs/hello.txt")
)

assert asset.file.name == "docs/hello.txt"
assert asset.file.url == "/media/docs/hello.txt"
assert asset.model_dump()["file"] == "docs/hello.txt"
```

By default, `FileField` also creates hidden embedded columns for:

- `<field>_size`
- `<field>_metadata`

Approval tracking can be enabled with `with_approval=True`, which adds
`<field>_approved`.

Projects that only want a single path/reference column can disable the embedded columns:

```python
class ExternalAsset(saffier.Model):
    path = saffier.FileField(
        null=True,
        with_size=False,
        with_metadata=False,
    )
```

## Image fields

`ImageField` uses the same storage-backed behavior as `FileField` and enables approval
tracking by default. When Pillow is installed, Saffier records image metadata such as
MIME type, format, width, and height.

```python
class Photo(saffier.Model):
    image = saffier.ImageField(null=True, image_formats=None)
```

Use `image_formats` and `approved_image_formats` to control which Pillow-recognized
formats can produce image metadata before and after approval.

## Storage configuration

The global storage registry reads from `settings.storages`.

```python
from saffier.conf import override_settings
from saffier.files import storages

with override_settings(
    storages={
        "default": {
            "backend": "saffier.core.files.storage.filesystem.FileSystemStorage",
            "options": {"location": "media", "base_url": "/media/"},
        }
    }
):
    storages.reload()
    storage = storages["default"]
```

Available storage-related settings:

- `media_root`
- `media_url`
- `storages`
- `file_upload_temp_dir`
- `file_upload_permissions`
- `file_upload_directory_permissions`
- `use_tz`

## Safe filenames and moves

The filesystem backend intentionally rejects path traversal attempts such as `../secret.txt`.

When a destination already exists, the storage backend allocates a safe alternative name instead of overwriting unexpectedly. File moves also fall back to a streamed copy when an atomic rename is not possible across filesystems.
