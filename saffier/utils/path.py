from __future__ import annotations

import os
import pathlib
import re
import secrets
import string
from os.path import abspath, dirname, join, normcase, sep
from typing import Any
from urllib.parse import quote

from saffier.exceptions import SuspiciousFileOperation


def safe_join(base: str, *paths: Any) -> str:
    """
    Join paths while preventing directory traversal outside the base path.
    """
    final_path = abspath(join(base, *paths))
    base_path = abspath(base)
    _validate_final_path(final_path, base_path)
    return final_path


def _validate_final_path(final_path: str, base_path: str) -> None:
    normalized_final_path = normcase(final_path)
    normalized_base_path = normcase(base_path)

    starts_with_base = normalized_final_path.startswith(normalized_base_path + sep)
    is_base_path = normalized_final_path == normalized_base_path
    base_is_dir = dirname(normalized_base_path) != normalized_base_path
    if not starts_with_base and not is_base_path and base_is_dir:
        raise SuspiciousFileOperation(
            f"The joined path ({final_path}) is located outside of the base path "
            f"component ({base_path})"
        )


def get_valid_filename(name: str) -> str:
    cleaned_name = str(name).strip().replace(" ", "_")
    cleaned_name = re.sub(r"(?u)[^-\w.]", "", cleaned_name)
    if cleaned_name in {"", ".", ".."}:
        raise SuspiciousFileOperation(f"Could not derive file name from '{name}'")
    return cleaned_name


def get_random_string(length: int = 10) -> str:
    letters = string.ascii_lowercase
    return "".join(secrets.choice(letters) for _ in range(length))


def validate_file_name(name: str, allow_relative_path: bool = False) -> str:
    base_name = os.path.basename(name)
    if base_name in {"", ".", ".."}:
        raise SuspiciousFileOperation(f"Could not derive file name from '{name}'")

    if allow_relative_path:
        path = pathlib.PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise SuspiciousFileOperation(f"Detected path traversal attempt in '{name}'")
    elif name != base_name:
        raise SuspiciousFileOperation(f"File name '{name}' includes path elements")

    return name


def filepath_to_uri(path: str | None) -> str:
    if not path:
        return ""
    return quote(str(path).replace("\\", "/"), safe="/~!*()'")


__all__ = [
    "filepath_to_uri",
    "get_random_string",
    "get_valid_filename",
    "safe_join",
    "validate_file_name",
]
