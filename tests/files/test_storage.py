from __future__ import annotations

import os

import pytest

import saffier
from saffier.exceptions import InvalidStorageError, SuspiciousFileOperation


def test_storage_handler_builds_and_caches_storage(tmp_path) -> None:
    handler = saffier.files.StorageHandler(
        {
            "local": {
                "backend": "saffier.core.files.storage.filesystem.FileSystemStorage",
                "options": {"location": str(tmp_path), "base_url": "/media/"},
            }
        }
    )

    storage = handler["local"]

    assert isinstance(storage, saffier.files.FileSystemStorage)
    assert storage.name == "local"
    assert handler["local"] is storage


def test_storage_handler_rejects_missing_alias() -> None:
    handler = saffier.files.StorageHandler({})

    with pytest.raises(InvalidStorageError, match="Could not find config"):
        handler["missing"]


def test_storage_handler_rejects_invalid_backend() -> None:
    handler = saffier.files.StorageHandler({"broken": {"backend": object()}})

    with pytest.raises(InvalidStorageError, match="Invalid storage backend"):
        handler["broken"]


def test_storage_handler_clear_discards_cached_instances_only(tmp_path) -> None:
    handler = saffier.files.StorageHandler(
        {
            "local": {
                "backend": saffier.files.FileSystemStorage,
                "options": {"location": str(tmp_path)},
            }
        }
    )

    first = handler["local"]
    handler.clear()

    second = handler["local"]

    assert second.name == "local"
    assert second is not first


def test_filesystem_storage_save_open_delete_and_url(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path, base_url="/media/")

    name = storage.save(b"hello world", "nested/file name.txt")

    assert name == "nested/file_name.txt"
    assert storage.exists(name)
    assert storage.path(name) == os.path.join(str(tmp_path), "nested", "file_name.txt")
    assert storage.url(name) == "/media/nested/file_name.txt"
    assert storage.size(name) == 11

    directories, files = storage.listdir("nested")
    assert directories == []
    assert files == ["file_name.txt"]

    with storage.open(name) as file:
        assert file.read() == b"hello world"

    storage.delete(name)
    assert not storage.exists(name)


def test_filesystem_storage_generates_alternative_name_on_collision(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path)

    first = storage.save(b"first", "demo.txt")
    second = storage.save(b"second", "demo.txt")

    assert first == "demo.txt"
    assert second != first
    assert second.endswith(".txt")

    with storage.open(second) as file:
        assert file.read() == b"second"


def test_filesystem_storage_rejects_path_traversal(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path)

    with pytest.raises(SuspiciousFileOperation, match="path traversal"):
        storage.save(b"hello", "../outside.txt")


def test_filesystem_storage_returns_tz_aware_datetimes_by_default(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path)
    name = storage.save(b"hello", "demo.txt")

    assert storage.get_accessed_time(name).tzinfo is not None
    assert storage.get_created_time(name).tzinfo is not None
    assert storage.get_modified_time(name).tzinfo is not None
