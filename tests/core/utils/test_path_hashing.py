from __future__ import annotations

import re
from pathlib import Path

import pytest

from saffier.exceptions import SuspiciousFileOperation
from saffier.utils.hashing import hash_to_identifier, hash_to_identifier_as_string
from saffier.utils.path import (
    filepath_to_uri,
    get_random_string,
    get_valid_filename,
    safe_join,
    validate_file_name,
)


def test_hash_to_identifier_is_stable_and_prefixed() -> None:
    value = hash_to_identifier("table-key")
    assert value.startswith("_")
    assert value == hash_to_identifier("table-key")
    assert value != hash_to_identifier("other-key")


def test_hash_to_identifier_as_string_matches_runtime_implementation() -> None:
    namespace: dict[str, object] = {}
    exec(hash_to_identifier_as_string, namespace)
    inline_impl = namespace["hash_to_identifier"]
    assert callable(inline_impl)
    assert inline_impl("abc") == hash_to_identifier("abc")


def test_safe_join_prevents_path_traversal(tmp_path: Path) -> None:
    joined = safe_join(str(tmp_path), "nested", "file.txt")
    assert joined.startswith(str(tmp_path))

    with pytest.raises(SuspiciousFileOperation):
        safe_join(str(tmp_path), "..", "outside.txt")


def test_get_valid_filename_and_validate_file_name() -> None:
    assert get_valid_filename(" My File!.txt ") == "My_File.txt"
    with pytest.raises(SuspiciousFileOperation):
        get_valid_filename("..")

    assert validate_file_name("plain.txt") == "plain.txt"
    assert validate_file_name("nested/path.txt", allow_relative_path=True) == "nested/path.txt"

    with pytest.raises(SuspiciousFileOperation):
        validate_file_name("nested/path.txt")
    with pytest.raises(SuspiciousFileOperation):
        validate_file_name("../etc/passwd", allow_relative_path=True)


def test_filepath_to_uri_and_random_string() -> None:
    assert filepath_to_uri(r"folder\my file.txt") == "folder/my%20file.txt"
    assert filepath_to_uri(None) == ""

    token = get_random_string(12)
    assert len(token) == 12
    assert re.fullmatch(r"[a-z]{12}", token) is not None
