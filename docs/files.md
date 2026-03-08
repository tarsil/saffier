# Files and Storage

Saffier now exposes a Python-native file and storage subsystem under `saffier.files`.

This closes the core storage gap with Edgy without introducing any Pydantic dependency.

## What it provides

- `File`: a lightweight wrapper around file-like objects and stored files.
- `ContentFile`: an in-memory binary file.
- `FileUpload`: a Python-native serialized upload payload using `name` and raw/base64 `content`.
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

## Serialized uploads without Pydantic

Edgy models file uploads with a Pydantic structure. In Saffier the equivalent is a plain Python object:

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

## Current ORM boundary

This subsystem is available today for standalone storage usage and for Saffier-native integrations.

`FileField` and `ImageField` in Saffier still behave as lightweight path/reference fields. The richer ORM-managed `FieldFile` layer from Edgy is a separate parity track and needs to be adapted to Saffier’s model lifecycle without importing Pydantic assumptions.
