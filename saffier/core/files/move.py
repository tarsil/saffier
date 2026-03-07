from __future__ import annotations

import contextlib
import os
from shutil import copymode, copystat

from . import locks

__all__ = ["file_move_safe"]


def _samefile(src: str, dst: str) -> bool:
    if hasattr(os.path, "samefile"):
        with contextlib.suppress(OSError):
            return os.path.samefile(src, dst)
        return False
    return os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst))


def file_move_safe(
    old_file_name: str,
    new_file_name: str,
    chunk_size: int = 1024 * 64,
    allow_overwrite: bool = False,
) -> None:
    if _samefile(old_file_name, new_file_name):
        return

    if not allow_overwrite and os.path.exists(new_file_name):
        raise FileExistsError(
            f"Destination file {new_file_name!r} exists and allow_overwrite is False."
        )

    try:
        os.rename(old_file_name, new_file_name)
        return
    except OSError:
        pass

    fd = os.open(
        new_file_name,
        os.O_WRONLY
        | os.O_CREAT
        | getattr(os, "O_BINARY", 0)
        | (0 if allow_overwrite else os.O_EXCL),
    )
    try:
        locks.lock(fd, locks.LOCK_EX)
        with open(old_file_name, "rb") as source, os.fdopen(fd, "wb") as destination:
            fd = -1
            while True:
                current_chunk = source.read(chunk_size)
                if not current_chunk:
                    break
                destination.write(current_chunk)
    finally:
        if fd != -1:
            os.close(fd)

    try:
        copystat(old_file_name, new_file_name)
    except PermissionError:
        with contextlib.suppress(PermissionError):
            copymode(old_file_name, new_file_name)

    try:
        os.remove(old_file_name)
    except PermissionError as exc:
        if getattr(exc, "winerror", 0) != 32:
            raise
