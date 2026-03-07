from __future__ import annotations

from io import BytesIO

import pytest

import saffier
from saffier.conf import override_settings
from saffier.core.files import locks
from saffier.core.files.storage.base import Storage
from saffier.exceptions import SuspiciousFileOperation


class MemoryStorage(Storage):
    def __init__(self) -> None:
        self._saved: dict[str, bytes] = {}
        self._reserved: set[str] = set()

    def _open(self, name: str, mode: str):
        del mode
        return saffier.files.File(BytesIO(self._saved[name]), name=name, storage=self)

    def _save(self, content: saffier.files.File, name: str = "") -> str:
        self._saved[name] = b"".join(content.chunks())
        return name

    def reserve_name(self, name: str) -> bool:
        if name in self._saved or name in self._reserved:
            return False
        self._reserved.add(name)
        return True

    def unreserve_name(self, name: str) -> bool:
        if name in self._reserved:
            self._reserved.remove(name)
            return True
        return False

    def delete(self, name: str) -> None:
        self._saved.pop(name, None)

    def exists(self, name: str) -> bool:
        return name in self._saved

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        return [], [name for name in self._saved if name.startswith(path)]

    def size(self, name: str) -> int:
        return len(self._saved[name])


class BareStorage(MemoryStorage):
    pass


def test_storage_base_save_wraps_string_bytes_and_file_like() -> None:
    storage = MemoryStorage()
    assert storage.save("hello", "note.txt") == "note.txt"
    assert storage.save(b"raw", "raw.bin") == "raw.bin"

    stream = BytesIO(b"stream")
    stream.name = "stream.bin"  # type: ignore[attr-defined]
    assert storage.save(stream) == "stream.bin"

    assert storage._saved == {
        "note.txt": b"hello",
        "raw.bin": b"raw",
        "stream.bin": b"stream",
    }


def test_storage_base_sanitizes_relative_paths_without_flattening() -> None:
    storage = MemoryStorage()

    assert storage.sanitize_name("avatars/my file.png") == "avatars/my_file.png"


def test_storage_base_helpers_raise_by_default() -> None:
    storage = BareStorage()

    with pytest.raises(NotImplementedError, match="absolute paths"):
        storage.path("demo.txt")
    with pytest.raises(NotImplementedError, match="'url'"):
        storage.url("demo.txt")
    with pytest.raises(NotImplementedError, match="'accessed_time'"):
        storage.get_accessed_time("demo.txt")
    with pytest.raises(NotImplementedError, match="'created_time'"):
        storage.get_created_time("demo.txt")
    with pytest.raises(NotImplementedError, match="'modified_time'"):
        storage.get_modified_time("demo.txt")


def test_storage_get_available_name_raises_when_max_length_cannot_be_satisfied() -> None:
    storage = MemoryStorage()

    with pytest.raises(SuspiciousFileOperation, match="available filename"):
        storage.get_available_name(
            "very-long-filename.txt", max_length=8, multi_process_safe=False
        )


def test_storage_value_or_setting_prefers_explicit_value() -> None:
    assert MemoryStorage.value_or_setting("explicit", "fallback") == "explicit"
    assert MemoryStorage.value_or_setting(None, "fallback") == "fallback"


def test_file_default_storage_alias_uses_global_registry(tmp_path) -> None:
    with override_settings(
        storages={
            "default": {
                "backend": "saffier.core.files.storage.filesystem.FileSystemStorage",
                "options": {"location": str(tmp_path), "base_url": "/media/"},
            }
        }
    ):
        saffier.files.storages.reload()

        file = saffier.files.File(b"hello", name="demo.txt")

        assert file.storage.name == "default"
        assert file.read() == b"hello"

    saffier.files.storages.reload()


def test_file_runtime_helpers_cover_read_seek_write_and_close(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path, base_url="/media/")
    path = tmp_path / "demo.bin"
    path.write_bytes(b"abc")

    with open(path, "rb+") as handle:
        file = saffier.files.File(handle, name="demo.bin", storage=storage)

        assert repr(file) == "<File: demo.bin>"
        assert bool(file) is True
        assert file.path.endswith("demo.bin")
        assert file.url == "/media/demo.bin"
        assert file.readable() is True
        assert file.writable() is True
        assert file.seekable() is True
        assert len(file) == 3
        assert file.seek(3) == 3
        assert file.tell() == 3
        assert file.write(b"d") == 1
        handle.flush()
        assert len(file) == 4
        file.close(keep_size=True)
        assert file.closed is True
        assert file.size == 4


def test_content_file_helpers_and_closed_file_flags() -> None:
    file = saffier.files.ContentFile(b"payload", name="payload.bin")

    assert str(file) == "Raw content"
    assert file.multiple_chunks(chunk_size=2) is True
    assert file.open().read() == b"payload"
    file.close()
    assert file.size == 7

    closed = saffier.files.File(name="", storage=MemoryStorage())
    assert bool(closed) is False
    assert len(closed) == 0
    assert closed.readable() is False
    assert closed.writable() is False
    assert closed.seekable() is False


def test_file_size_error_for_stream_without_positioning_support() -> None:
    class ReadOnlyStream:
        def read(self, amount: int | None = None) -> bytes:
            del amount
            return b""

    file = saffier.files.File(ReadOnlyStream(), name="opaque.bin", storage=MemoryStorage())

    with pytest.raises(AttributeError, match="Unable to determine"):
        _ = file.size


def test_lock_helpers_lock_and_unlock_file(tmp_path) -> None:
    path = tmp_path / "locked.txt"
    path.write_bytes(b"lock")

    with open(path, "rb+") as handle:
        assert locks._fd(handle) == handle.fileno()
        assert locks.lock(handle, locks.LOCK_EX) is True
        assert locks.unlock(handle) is True
