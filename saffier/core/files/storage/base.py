from __future__ import annotations

import os
import pathlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, TypeVar

from saffier.core.files.base import ContentFile, File
from saffier.exceptions import SuspiciousFileOperation
from saffier.utils.path import get_random_string, get_valid_filename, validate_file_name

_ArgValue = TypeVar("_ArgValue")
_ArgSetting = TypeVar("_ArgSetting")


class Storage(ABC):
    name: str = ""

    @staticmethod
    def value_or_setting(
        value: _ArgValue,
        setting: _ArgSetting,
    ) -> _ArgValue | _ArgSetting:
        return setting if value is None else value

    @abstractmethod
    def _open(self, name: str, mode: str) -> Any: ...

    def open(self, name: str, mode: str | None = None) -> Any:
        return self._open(name, mode or "rb")

    @abstractmethod
    def _save(self, content: File, name: str = "") -> str: ...

    def save(self, content: Any, name: str = "") -> str:
        if not name:
            name = getattr(content, "name", "")
        name = self.sanitize_name(name)

        if isinstance(content, str):
            content = ContentFile(content.encode("utf8"), name)
        elif isinstance(content, bytes):
            content = ContentFile(content, name)
        elif not hasattr(content, "chunks"):
            content = File(content, name)

        final_name = self._save(content, name)
        content.name = final_name
        return final_name

    @abstractmethod
    def reserve_name(self, name: str) -> bool: ...

    @abstractmethod
    def unreserve_name(self, name: str) -> bool: ...

    def sanitize_name(self, name: str) -> str:
        validate_file_name(name, allow_relative_path=True)
        normalized = str(name).replace("\\", "/")
        directory, filename = os.path.split(normalized)
        sanitized_name = get_valid_filename(filename)
        if not directory:
            return sanitized_name
        cleaned_directory = pathlib.PurePosixPath(directory)
        if ".." in cleaned_directory.parts:
            raise SuspiciousFileOperation(f"Detected path traversal attempt in '{directory}'")
        return str(cleaned_directory / sanitized_name)

    def get_alternative_name(self, file_root: str, file_ext: str) -> str:
        return f"{file_root}_{get_random_string(7)}{file_ext}"

    def get_available_name(
        self,
        name: str,
        max_length: int | None = None,
        overwrite: bool = False,
        multi_process_safe: bool | None = None,
    ) -> str:
        if multi_process_safe is None:
            multi_process_safe = not overwrite

        name = str(name).replace("\\", "/")
        dir_name, file_name = os.path.split(name)
        if ".." in pathlib.PurePosixPath(dir_name).parts:
            raise SuspiciousFileOperation(f"Detected path traversal attempt in '{dir_name}'")

        validate_file_name(file_name)
        file_root, file_ext = os.path.splitext(file_name)

        if multi_process_safe:
            file_root = f"{os.getpid() or 0:x}_{file_root}"

        while (max_length and len(name) > max_length) or (
            not self.reserve_name(name) and not overwrite
        ):
            if overwrite:
                name = os.path.join(dir_name, f"{file_root}{file_ext}")
            else:
                name = os.path.join(dir_name, self.get_alternative_name(file_root, file_ext))

            if max_length is not None:
                truncation = len(name) - max_length
                if truncation > 0:
                    file_root = file_root[:-truncation]
                    if not file_root:
                        raise SuspiciousFileOperation(
                            f'Storage can not find an available filename for "{name}". '
                            "Please make sure that the corresponding file field allows "
                            'sufficient "max_length".'
                        )
                    if overwrite:
                        name = os.path.join(dir_name, f"{file_root}{file_ext}")
                    else:
                        name = os.path.join(
                            dir_name, self.get_alternative_name(file_root, file_ext)
                        )
        return str(name).replace("\\", "/")

    def path(self, name: str) -> str:
        raise NotImplementedError("This backend doesn't support absolute paths.")

    @abstractmethod
    def delete(self, name: str) -> None: ...

    @abstractmethod
    def exists(self, name: str) -> bool: ...

    @abstractmethod
    def listdir(self, path: str) -> tuple[list[str], list[str]]: ...

    @abstractmethod
    def size(self, name: str) -> int: ...

    def url(self, name: str) -> str:
        raise NotImplementedError("This backend doesn't support 'url'.")

    def get_accessed_time(self, name: str) -> datetime:
        raise NotImplementedError("This backend doesn't support 'accessed_time'.")

    def get_created_time(self, name: str) -> datetime:
        raise NotImplementedError("This backend doesn't support 'created_time'.")

    def get_modified_time(self, name: str) -> datetime:
        raise NotImplementedError("This backend doesn't support 'modified_time'.")
