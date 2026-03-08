from __future__ import annotations

import base64
import contextlib
import os
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from functools import cached_property
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, cast

from saffier.exceptions import FileOperationError, SuspiciousFileOperation

if TYPE_CHECKING:
    from .storage.base import Storage


def _get_storage(storage: str) -> Storage:
    from .storage import storages

    return storages[storage]


@dataclass(slots=True)
class FileUpload:
    """
    Python-native file payload equivalent for serialized uploads.
    """

    name: str
    content: bytes

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FileUpload.name cannot be empty.")
        if not isinstance(self.content, bytes):
            raise TypeError("FileUpload.content must be bytes.")

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> FileUpload:
        if "name" not in data or "content" not in data:
            raise ValueError("FileUpload data must include 'name' and 'content'.")
        name = str(data["name"])
        raw_content = data["content"]
        if isinstance(raw_content, str):
            try:
                content = base64.b64decode(raw_content.encode("ascii"), validate=True)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid base64 file content.") from exc
        elif isinstance(raw_content, bytes):
            content = raw_content
        else:
            raise TypeError("FileUpload.content must be bytes or base64 text.")
        return cls(name=name, content=content)

    def to_file(self) -> ContentFile:
        return ContentFile(self.content, name=self.name)


class File:
    name: str
    file: BinaryIO | None
    storage: Storage
    DEFAULT_CHUNK_SIZE: ClassVar[int] = 64 * 2**10
    mode: str = "rb"

    def __init__(
        self,
        file: BinaryIO | bytes | None | File = None,
        name: str = "",
        storage: Storage | str | None = None,
    ) -> None:
        if isinstance(file, File):
            file = file.open("rb").file
        elif isinstance(file, bytes):
            file = BytesIO(file)
        self.file = file

        if not storage:
            storage = "default"
        if isinstance(storage, str):
            storage = _get_storage(storage)
        self.storage = storage

        if not name:
            name = getattr(file, "name", "")
        self.name = name or ""
        if hasattr(file, "mode"):
            self.mode = file.mode

    def __eq__(self, other: str | File) -> bool:
        if hasattr(other, "name"):
            return self.name == cast("File", other).name
        return self.name == other

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self or 'None'}>"

    def __bool__(self) -> bool:
        return bool(self.name or self.file is not None)

    @cached_property
    def size(self) -> int:
        if self.file is None:
            return 0
        if hasattr(self.file, "size"):
            return cast(int, self.file.size)
        if hasattr(self.file, "name"):
            try:
                return self.storage.size(self.file.name)
            except (OSError, TypeError, SuspiciousFileOperation):
                pass
        if hasattr(self.file, "tell") and hasattr(self.file, "seek"):
            pos = self.file.tell()
            self.file.seek(0, os.SEEK_END)
            size = self.file.tell()
            self.file.seek(pos)
            return size
        raise AttributeError("Unable to determine the file's size.")

    def __len__(self) -> int:
        return self.size

    @property
    def closed(self) -> bool:
        return not self.file or self.file.closed

    @property
    def path(self) -> str:
        return self.storage.path(self.name)

    @property
    def url(self) -> str:
        return self.storage.url(self.name)

    def chunks(self, chunk_size: int | None = None) -> Generator[bytes, None, None]:
        assert self.file is not None, "File is closed"
        chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE
        with contextlib.suppress(AttributeError, OSError):
            self.file.seek(0)
        while True:
            data = self.file.read(chunk_size)
            if not data:
                break
            yield data

    def multiple_chunks(self, chunk_size: int | None = None) -> bool:
        if chunk_size is None:
            chunk_size = self.DEFAULT_CHUNK_SIZE
        return self.size > chunk_size

    def __enter__(self) -> File:
        assert self.file is not None, "File is closed"
        return self

    def __exit__(self, exc_type: Exception, exc_value: Any, tb: Any) -> None:
        self.close()

    def open(self, mode: str | None = None) -> File:
        if not self.closed:
            with contextlib.suppress(AttributeError, OSError):
                self.file.seek(0)
        elif self.name and self.storage.exists(self.name):
            self.file = self.storage.open(self.name, mode or self.mode).file
        else:
            raise FileOperationError("The file cannot be reopened.")
        return self

    def readable(self) -> bool:
        if self.closed:
            return False
        assert self.file is not None
        if hasattr(self.file, "readable"):
            return self.file.readable()
        return True

    def writable(self) -> bool:
        if self.closed:
            return False
        assert self.file is not None
        if hasattr(self.file, "writable"):
            return self.file.writable()
        return "w" in getattr(self.file, "mode", "")

    def seekable(self) -> bool:
        if self.closed:
            return False
        assert self.file is not None
        if hasattr(self.file, "seekable"):
            return self.file.seekable()
        return False

    def seek(self, offset: int, whence: int = 0) -> int:
        assert self.seekable()
        assert self.file is not None
        return self.file.seek(offset, whence)

    def tell(self) -> int:
        assert self.file is not None
        return self.file.tell()

    def read(self, amount: int | None = None) -> bytes:
        assert self.file is not None
        return self.file.read(amount)

    def write(self, data: bytes) -> int:
        assert self.file is not None
        self.__dict__.pop("size", None)
        return self.file.write(data)

    def close(self, keep_size: bool = False) -> None:
        if self.file is None:
            return
        self.file.close()
        self.file = None
        if not keep_size:
            self.__dict__.pop("size", None)


class ContentFile(File):
    file: BinaryIO

    def __init__(self, content: bytes, name: str = "") -> None:
        super().__init__(file=BytesIO(content), name=name)
        self.size = len(content)

    def __str__(self) -> str:
        return "Raw content"

    def open(self, mode: str | Any = None) -> ContentFile:
        self.file.seek(0)
        return self

    def close(self, keep_size: bool = False) -> None:
        if not keep_size:
            self.__dict__.pop("size", None)


__all__ = ["ContentFile", "File", "FileUpload"]
