from __future__ import annotations

from pathlib import Path

from marius.tools.filesystem import LIST_DIR, READ_FILE, WRITE_FILE


def test_read_file_returns_content(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("bonjour monde", encoding="utf-8")
    result = READ_FILE.handler({"path": str(f)})
    assert result.ok is True
    assert "bonjour monde" in result.summary


def test_read_file_missing_path_arg():
    result = READ_FILE.handler({})
    assert result.ok is False
    assert "path" in result.summary


def test_read_file_not_found():
    result = READ_FILE.handler({"path": "/nonexistent/file.txt"})
    assert result.ok is False
    assert result.error == "file_not_found"


def test_read_file_produces_artifact(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("contenu", encoding="utf-8")
    result = READ_FILE.handler({"path": str(f)})
    assert len(result.artifacts) == 1
    assert result.artifacts[0].data["content"] == "contenu"


def test_list_dir_returns_entries(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    result = LIST_DIR.handler({"path": str(tmp_path)})
    assert result.ok is True
    assert "a.py" in result.summary
    assert "sub" in result.summary


def test_list_dir_default_path():
    result = LIST_DIR.handler({})
    assert result.ok is True


def test_list_dir_not_found():
    result = LIST_DIR.handler({"path": "/nonexistent/dir"})
    assert result.ok is False
    assert result.error == "dir_not_found"


def test_write_file_creates_file(tmp_path):
    dest = tmp_path / "output.txt"
    result = WRITE_FILE.handler({"path": str(dest), "content": "hello"})
    assert result.ok is True
    assert dest.read_text() == "hello"


def test_write_file_creates_parent_dirs(tmp_path):
    dest = tmp_path / "deep" / "nested" / "file.txt"
    result = WRITE_FILE.handler({"path": str(dest), "content": "data"})
    assert result.ok is True
    assert dest.exists()


def test_write_file_missing_path_arg():
    result = WRITE_FILE.handler({"content": "x"})
    assert result.ok is False
