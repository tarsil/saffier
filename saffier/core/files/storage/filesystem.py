from __future__ import annotations

import contextlib
import os
from datetime import datetime, timezone
from functools import cached_property
from threading import Lock
from typing import Any, BinaryIO, cast
from urllib.parse import urljoin

from saffier.conf import settings
from saffier.core.files.base import File
from saffier.core.files.move import file_move_safe
from saffier.utils.path import filepath_to_uri, safe_join

from .. import locks
from .base import Storage


class FileSystemStorage(Storage):
    OS_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)

    def __init__(
        self,
        location: str | os.PathLike[str] | None = None,
        base_url: str | None = None,
        file_permissions_mode: int | None = None,
        directory_permissions_mode: int | None = None,
    ) -> None:
        self._location = location
        self._base_url = base_url
        self._file_permissions_mode = file_permissions_mode
        self._directory_permissions_mode = directory_permissions_mode
        self._name_lock = Lock()
        self._name_dict: dict[str, datetime] = {}

    def reserve_name(self, name: str) -> bool:
        with self._name_lock:
            if not self.exists(name) and name not in self._name_dict:
                self._name_dict[name] = datetime.now(timezone.utc)
                return True
        return False

    def unreserve_name(self, name: str) -> bool:
        with self._name_lock:
            if name in self._name_dict:
                del self._name_dict[name]
                return True
        return False

    @cached_property
    def base_location(self) -> str:
        return os.path.normpath(
            os.fspath(self.value_or_setting(self._location, settings.media_root))
        )

    @cached_property
    def location(self) -> str:
        return os.path.abspath(self.base_location)

    @cached_property
    def base_url(self) -> str:
        base_url = self.value_or_setting(self._base_url, settings.media_url)
        if base_url and not str(base_url).endswith("/"):
            base_url = f"{base_url}/"
        return cast(str, base_url)

    @cached_property
    def file_permissions_mode(self) -> int | None:
        return cast(
            int | None,
            self.value_or_setting(self._file_permissions_mode, settings.file_upload_permissions),
        )

    @cached_property
    def directory_permissions_mode(self) -> int | None:
        return cast(
            int | None,
            self.value_or_setting(
                self._directory_permissions_mode,
                settings.file_upload_directory_permissions,
            ),
        )

    def _open(self, name: str, mode: str) -> File:
        return File(cast(BinaryIO, open(self.path(name), mode)), name=name, storage=self)

    def _save(self, content: File, name: str) -> str:
        full_path = self._get_full_path(name)
        self._create_directory(full_path)
        final_full_path = self._save_content(full_path, name, content)
        self._set_permissions(final_full_path)
        return self._get_relative_path(final_full_path)

    def _get_full_path(self, name: str) -> str:
        return self.path(name)

    def _create_directory(self, full_path: str) -> None:
        directory = os.path.dirname(full_path)
        os.makedirs(directory, mode=self.directory_permissions_mode or 0o777, exist_ok=True)

    def _save_content(self, full_path: str, name: str, content: Any) -> str:
        reserved_name: str | None = None
        while True:
            try:
                if hasattr(content, "temporary_file_path"):
                    file_move_safe(content.temporary_file_path(), full_path)
                else:
                    descriptor = os.open(full_path, self.OS_OPEN_FLAGS, 0o666)
                    try:
                        locks.lock(descriptor, locks.LOCK_EX)
                        with os.fdopen(descriptor, "wb") as file_object:
                            descriptor = -1
                            for chunk in content.chunks():
                                file_object.write(chunk)
                    finally:
                        if descriptor != -1:
                            os.close(descriptor)
            except FileExistsError:
                if reserved_name is not None:
                    self.unreserve_name(reserved_name)
                name = self.get_available_name(name)
                reserved_name = name
                full_path = self.path(name)
            else:
                if reserved_name is not None:
                    self.unreserve_name(reserved_name)
                break
        return full_path

    def _set_permissions(self, full_path: str) -> None:
        if self.file_permissions_mode is not None:
            os.chmod(full_path, self.file_permissions_mode)

    def _get_relative_path(self, full_path: str) -> str:
        name = os.path.relpath(full_path, self.location)
        self._ensure_location_group_id(full_path)
        return str(name).replace("\\", "/")

    def _ensure_location_group_id(self, full_path: str) -> None:
        if os.name == "posix":
            file_gid = os.stat(full_path).st_gid
            location_gid = os.stat(self.location).st_gid
            if file_gid != location_gid:
                with contextlib.suppress(PermissionError):
                    os.chown(full_path, uid=-1, gid=location_gid)

    def delete(self, name: str) -> None:
        if not name:
            raise ValueError("The name must be given to delete().")

        full_path = self.path(name)
        try:
            if os.path.isdir(full_path):
                os.rmdir(full_path)
            else:
                os.remove(full_path)
        except FileNotFoundError:
            pass

    def exists(self, name: str) -> bool:
        return os.path.lexists(self.path(name))

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        full_path = self.path(path)
        directories: list[str] = []
        files: list[str] = []
        with os.scandir(full_path) as entries:
            for entry in entries:
                if entry.is_dir():
                    directories.append(entry.name)
                else:
                    files.append(entry.name)
        return directories, files

    def path(self, name: str) -> str:
        return safe_join(self.location, name)

    def size(self, name: str) -> int:
        return os.path.getsize(self.path(name))

    def url(self, name: str) -> str:
        if not self.base_url:
            raise ValueError("This file is not accessible via a URL.")
        url = filepath_to_uri(name)
        return urljoin(self.base_url, url.lstrip("/"))

    @staticmethod
    def _datetime_from_timestamp(ts: float) -> datetime:
        tz = timezone.utc if settings.use_tz else None
        return datetime.fromtimestamp(ts, tz=tz)

    def get_accessed_time(self, name: str) -> datetime:
        return self._datetime_from_timestamp(os.path.getatime(self.path(name)))

    def get_created_time(self, name: str) -> datetime:
        return self._datetime_from_timestamp(os.path.getctime(self.path(name)))

    def get_modified_time(self, name: str) -> datetime:
        return self._datetime_from_timestamp(os.path.getmtime(self.path(name)))
