"""
Portable file locking utilities.
"""

from __future__ import annotations

import os
from typing import IO, Any

__all__ = ("LOCK_EX", "LOCK_NB", "LOCK_SH", "lock", "unlock")


def _fd(file_or_fd: IO[bytes] | Any) -> Any:
    return file_or_fd.fileno() if hasattr(file_or_fd, "fileno") else file_or_fd


if os.name == "nt":  # pragma: no cover
    import msvcrt
    from ctypes import POINTER, Structure, Union, WinDLL, byref, c_int64, c_ulong, c_void_p, sizeof
    from ctypes.wintypes import BOOL, DWORD, HANDLE

    LOCK_SH = 0
    LOCK_NB = 0x1
    LOCK_EX = 0x2

    ULONG_PTR = c_int64 if sizeof(c_ulong) != sizeof(c_void_p) else c_ulong
    PVOID = c_void_p

    class _OFFSET(Structure):
        _fields_ = [("Offset", DWORD), ("OffsetHigh", DWORD)]

    class _OFFSET_UNION(Union):
        _anonymous_ = ["_offset"]
        _fields_ = [("_offset", _OFFSET), ("Pointer", PVOID)]

    class OVERLAPPED(Structure):
        _anonymous_ = ["_offset_union"]
        _fields_ = [
            ("Internal", ULONG_PTR),
            ("InternalHigh", ULONG_PTR),
            ("_offset_union", _OFFSET_UNION),
            ("hEvent", HANDLE),
        ]

    LPOVERLAPPED = POINTER(OVERLAPPED)

    kernel32 = WinDLL("kernel32")
    LockFileEx = kernel32.LockFileEx
    LockFileEx.restype = BOOL
    LockFileEx.argtypes = [HANDLE, DWORD, DWORD, DWORD, DWORD, LPOVERLAPPED]
    UnlockFileEx = kernel32.UnlockFileEx
    UnlockFileEx.restype = BOOL
    UnlockFileEx.argtypes = [HANDLE, DWORD, DWORD, DWORD, LPOVERLAPPED]

    def lock(file_or_fd: IO[bytes] | Any, flags: int) -> bool:
        handle = msvcrt.get_osfhandle(_fd(file_or_fd))
        overlapped = OVERLAPPED()
        return bool(LockFileEx(handle, flags, 0, 0, 0xFFFF0000, byref(overlapped)))

    def unlock(file_or_fd: IO[bytes] | Any) -> bool:
        handle = msvcrt.get_osfhandle(_fd(file_or_fd))
        overlapped = OVERLAPPED()
        return bool(UnlockFileEx(handle, 0, 0, 0xFFFF0000, byref(overlapped)))

else:
    try:
        import fcntl

        LOCK_SH = fcntl.LOCK_SH
        LOCK_NB = fcntl.LOCK_NB
        LOCK_EX = fcntl.LOCK_EX
    except (ImportError, AttributeError):  # pragma: no cover
        LOCK_EX = LOCK_SH = LOCK_NB = 0

        def lock(file_or_fd: IO[bytes] | Any, flags: int) -> bool:
            del file_or_fd, flags
            return False

        def unlock(file_or_fd: IO[bytes] | Any) -> bool:
            del file_or_fd
            return True

    else:

        def lock(file_or_fd: IO[bytes] | Any, flags: int) -> bool:
            try:
                fcntl.flock(_fd(file_or_fd), flags)
                return True
            except BlockingIOError:
                return False

        def unlock(file_or_fd: IO[bytes] | Any) -> bool:
            fcntl.flock(_fd(file_or_fd), fcntl.LOCK_UN)
            return True
