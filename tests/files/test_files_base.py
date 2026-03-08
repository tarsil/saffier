from __future__ import annotations

import base64
from io import BytesIO

import pytest

import saffier
from saffier.exceptions import FileOperationError


class NonSeekableBytesIO(BytesIO):
    def seek(self, offset: int, whence: int = 0) -> int:  # type: ignore[override]
        raise OSError("stream is not seekable")


def test_file_hash_uses_name() -> None:
    file_a = saffier.files.File(name="demo.txt")
    file_b = saffier.files.File(name="demo.txt")

    assert hash(file_a) == hash("demo.txt")
    assert file_a == file_b
    assert len({file_a, file_b}) == 1


def test_file_chunks_support_non_seekable_streams() -> None:
    file = saffier.files.File(file=NonSeekableBytesIO(b"abcdef"), name="demo.bin")

    assert list(file.chunks(chunk_size=2)) == [b"ab", b"cd", b"ef"]


def test_file_open_non_seekable_stream_keeps_working() -> None:
    file = saffier.files.File(file=NonSeekableBytesIO(b"abcdef"), name="demo.bin")

    reopened = file.open()

    assert reopened is file
    assert file.read(3) == b"abc"


def test_file_upload_from_base64_payload() -> None:
    upload = saffier.files.FileUpload.from_data(
        {
            "name": "hello.txt",
            "content": base64.b64encode(b"hello world").decode("ascii"),
        }
    )

    assert upload.name == "hello.txt"
    assert upload.content == b"hello world"
    assert upload.to_file().read() == b"hello world"


def test_file_upload_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="Invalid base64"):
        saffier.files.FileUpload.from_data({"name": "broken.txt", "content": "!!!"})


def test_file_open_missing_storage_target_raises(tmp_path) -> None:
    storage = saffier.files.FileSystemStorage(location=tmp_path)
    file = saffier.files.File(name="missing.txt", storage=storage)

    with pytest.raises(FileOperationError, match="cannot be reopened"):
        file.open()
