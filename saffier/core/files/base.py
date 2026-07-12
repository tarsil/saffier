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
    """
    Resolve a configured storage alias through Saffier's storage handler.

    The file primitives live below the public settings object to avoid creating
    storage backends at import time. Runtime resolution is therefore deferred
    until a ``File`` or ``FieldFile`` receives a string alias and needs the
    concrete backend for open, save, size, URL, or delete operations.

    Args:
        storage: Name of the storage backend configured in ``settings.storages``.

    Returns:
        Storage: Concrete storage backend associated with the alias.
    """
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
        """
        Return the byte size of the active or stored file.

        The value is resolved from the in-memory file object when one is open.
        For wrappers that only carry a stored name, Saffier asks the configured
        storage backend so database-loaded file references can still report a
        size without reopening content manually. A missing in-memory object and
        an unavailable stored object are treated as an empty file reference.
        """
        if self.file is None and self.name:
            try:
                return self.storage.size(self.name)
            except (OSError, TypeError, SuspiciousFileOperation, FileOperationError):
                return 0
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


class FieldFile(File):
    """File object bound to a Saffier model field.

    A ``FieldFile`` carries the stored file name plus optional metadata tracked
    by ``FileField`` columns. It deliberately remains string-comparable through
    ``File.__eq__`` so existing code that compares a file field to the stored
    path continues to behave naturally, while new code can open, save, delete,
    approve, or inspect metadata through the object.
    """

    def __init__(
        self,
        field: Any,
        file: BinaryIO | bytes | File | None = None,
        name: str = "",
        storage: Storage | str | None = None,
        *,
        size: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        approved: bool = True,
        committed: bool | None = None,
    ) -> None:
        """Bind a file wrapper to its owning field configuration.

        Args:
            field: ``FileField`` instance that owns this file value.
            file: Optional file content or another ``File`` wrapper.
            name: Stored file name.
            storage: Storage backend or storage alias.
            size: Persisted size override when loaded from the database.
            metadata: Persisted metadata mapping.
            approved: Whether the file is approved when approval tracking is
                enabled on the field.
            committed: Whether the current name already represents content
                saved in storage. When omitted, Saffier treats wrappers with
                immediate file content as pending uploads and wrappers built
                from stored names as committed values.
        """
        self.field = field
        self.metadata = dict(metadata or {})
        self.approved = approved
        self._committed = bool(name) if committed is None else committed
        if isinstance(file, File) and not name:
            name = file.name
        super().__init__(file=file, name=name, storage=storage or field.storage)
        if size is not None:
            self.size = size

    @property
    def committed(self) -> bool:
        """
        Report whether this wrapper already points at stored content.

        File fields use the flag to distinguish two very different values that
        both have a name: a database value such as ``"docs/report.pdf"`` and a
        newly assigned upload whose original name should be used as the storage
        target. The former can be written to the row unchanged, while the latter
        must be saved through the storage backend before its name is persisted.
        """
        return self._committed

    def save(
        self,
        content: File | BinaryIO | bytes,
        *,
        name: str | None = None,
        delete_old: bool = True,
        instance: Any | None = None,
    ) -> None:
        """Persist new content through the configured storage backend.

        Args:
            content: File content to store.
            name: Optional storage name. When omitted, the content name or the
                current ``FieldFile`` name is used.
            delete_old: Whether a previously stored name should be deleted after
                the new content is saved.
            instance: Model instance currently being persisted. It is forwarded
                to the field's name generator so applications can include model
                state in storage paths when that state is already available.
        """
        old_name = self.name
        if not isinstance(content, File):
            content = File(content, name=name or getattr(content, "name", "") or old_name)
        target_name = self.field.generate_name(instance, content, name or content.name or old_name)
        self.name = self.storage.save(content, target_name)
        self._committed = True
        self.__dict__.pop("size", None)
        self.metadata = self.field.extract_metadata(self)
        if delete_old and old_name and old_name != self.name:
            self.storage.delete(old_name)

    def delete(self) -> None:
        """
        Remove the stored object and reset the wrapper to an empty value.

        Deletion is intentionally local to the storage backend. Persisting the
        cleared database value remains the model's responsibility, which lets
        callers coordinate row updates and file deletion in the order that fits
        their application.
        """
        if self.name:
            self.storage.delete(self.name)
        self.name = ""
        self._committed = True
        self.metadata = {}
        self.__dict__.pop("size", None)

    def set_approved(self, approved: bool) -> None:
        """Update the approval flag and refresh approval-gated metadata.

        Args:
            approved: New approval state.
        """
        self.approved = approved
        self.metadata = self.field.extract_metadata(self)

    def to_file(self) -> File:
        """
        Create a plain file wrapper for storage-level APIs.

        The returned object drops field metadata and approval state, making it
        suitable for code that only needs the standard ``File`` interface while
        still using the same storage backend and stored name.
        """
        return File(name=self.name, storage=self.storage)

    def model_dump(self, **kwargs: Any) -> str:
        """
        Serialize the field-bound value as the stored file name.

        Model dumping historically exposed ``FileField`` values as their string
        path/reference value. Returning the name here preserves that public shape
        while still allowing runtime model attributes to expose richer
        ``FieldFile`` behavior. Extra keyword arguments are accepted so the
        method can be called by Saffier's generic serializer.
        """
        del kwargs
        return self.name


class ImageFieldFile(FieldFile):
    """
    Field-bound file wrapper with optional Pillow image helpers.

    Saffier keeps Pillow as an optional dependency. The wrapper therefore only
    imports Pillow when an image operation is requested by an ``ImageField`` or
    by user code, while all non-image file behavior remains available without
    importing the imaging stack.
    """

    def open_image(self) -> Any:
        """Open the stored file with Pillow.

        Returns:
            Any: Pillow image object. The return type is intentionally loose so
            Pillow remains an optional runtime dependency outside image-field
            usage.
        """
        from PIL import Image

        return Image.open(self.open("rb").file)


__all__ = ["ContentFile", "FieldFile", "File", "FileUpload", "ImageFieldFile"]
