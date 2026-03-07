from __future__ import annotations

from pathlib import Path

import pytest

from saffier.core.files.move import file_move_safe


def test_file_move_safe_falls_back_to_stream_copy(tmp_path, monkeypatch) -> None:
    source = Path(tmp_path / "source.txt")
    destination = Path(tmp_path / "destination.txt")
    source.write_bytes(b"payload")

    monkeypatch.setattr(
        "saffier.core.files.move.os.rename", lambda *_args: (_ for _ in ()).throw(OSError)
    )

    file_move_safe(str(source), str(destination))

    assert not source.exists()
    assert destination.read_bytes() == b"payload"


def test_file_move_safe_rejects_overwrite(tmp_path) -> None:
    source = Path(tmp_path / "source.txt")
    destination = Path(tmp_path / "destination.txt")
    source.write_bytes(b"payload")
    destination.write_bytes(b"other")

    with pytest.raises(FileExistsError):
        file_move_safe(str(source), str(destination))
