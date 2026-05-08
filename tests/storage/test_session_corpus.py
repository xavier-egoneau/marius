from __future__ import annotations

import re
from pathlib import Path

import pytest

from marius.storage.session_corpus import (
    SessionRecord,
    archive_session_file,
    list_unprocessed,
    write_session_file,
)


def _make_record(**kwargs) -> SessionRecord:
    defaults = dict(
        project="marius",
        cwd="/home/egza/Documents/projets/marius",
        opened_at="2026-05-08T14:32:00+00:00",
        closed_at="2026-05-08T16:14:00+00:00",
        turns=23,
    )
    defaults.update(kwargs)
    return SessionRecord(**defaults)


# ── write_session_file ────────────────────────────────────────────────────────


def test_write_creates_file(tmp_path: Path) -> None:
    record = _make_record()
    path = write_session_file(record, sessions_dir=tmp_path)
    assert path.exists()


def test_write_filename_from_opened_at(tmp_path: Path) -> None:
    record = _make_record(opened_at="2026-05-08T14:32:00+00:00")
    path = write_session_file(record, sessions_dir=tmp_path)
    assert path.name == "2026-05-08-14h32.md"


def test_write_content_has_frontmatter(tmp_path: Path) -> None:
    record = _make_record()
    path = write_session_file(record, sessions_dir=tmp_path)
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "project: marius" in content
    assert "turns: 23" in content
    assert content.strip().endswith("---")


def test_write_avoids_overwrite(tmp_path: Path) -> None:
    record = _make_record()
    path1 = write_session_file(record, sessions_dir=tmp_path)
    path2 = write_session_file(record, sessions_dir=tmp_path)
    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_write_creates_sessions_dir(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "nested" / "sessions"
    record = _make_record()
    write_session_file(record, sessions_dir=sessions_dir)
    assert sessions_dir.exists()


# ── list_unprocessed ──────────────────────────────────────────────────────────


def test_list_unprocessed_empty(tmp_path: Path) -> None:
    assert list_unprocessed(sessions_dir=tmp_path) == []


def test_list_unprocessed_returns_md_files(tmp_path: Path) -> None:
    write_session_file(_make_record(), sessions_dir=tmp_path)
    write_session_file(_make_record(opened_at="2026-05-08T15:00:00+00:00"), sessions_dir=tmp_path)
    results = list_unprocessed(sessions_dir=tmp_path)
    assert len(results) == 2


def test_list_unprocessed_excludes_archive(tmp_path: Path) -> None:
    path = write_session_file(_make_record(), sessions_dir=tmp_path)
    archive_session_file(path)
    results = list_unprocessed(sessions_dir=tmp_path)
    assert results == []


def test_list_unprocessed_sorted(tmp_path: Path) -> None:
    write_session_file(_make_record(opened_at="2026-05-08T15:00:00+00:00"), sessions_dir=tmp_path)
    write_session_file(_make_record(opened_at="2026-05-08T14:32:00+00:00"), sessions_dir=tmp_path)
    results = list_unprocessed(sessions_dir=tmp_path)
    names = [p.name for p in results]
    assert names == sorted(names)


# ── archive_session_file ──────────────────────────────────────────────────────


def test_archive_moves_file(tmp_path: Path) -> None:
    path = write_session_file(_make_record(), sessions_dir=tmp_path)
    archived = archive_session_file(path)
    assert not path.exists()
    assert archived.exists()
    assert archived.parent.name == "archive"


def test_archive_avoids_overwrite(tmp_path: Path) -> None:
    path1 = write_session_file(_make_record(), sessions_dir=tmp_path)
    path2 = write_session_file(_make_record(), sessions_dir=tmp_path)
    arch1 = archive_session_file(path1)
    arch2 = archive_session_file(path2)
    assert arch1 != arch2
    assert arch1.exists()
    assert arch2.exists()
