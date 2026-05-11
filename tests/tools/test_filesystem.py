from __future__ import annotations

from pathlib import Path

from marius.tools.filesystem import LIST_DIR, MAKE_DIR, MOVE_PATH, READ_FILE, WRITE_FILE


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


def test_read_file_not_found_suggests_same_filename(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wysiwyg").mkdir()
    (tmp_path / "wysiwyg" / "checks.html").write_text("<html></html>", encoding="utf-8")

    result = READ_FILE.handler({"path": "./checks.html"})

    assert result.ok is False
    assert result.error == "file_not_found"
    assert "wysiwyg/checks.html" in result.summary


def test_read_file_not_found_prioritizes_requested_suffix(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "core.js").write_text("other", encoding="utf-8")
    (tmp_path / "wysiwyg" / "js").mkdir(parents=True)
    (tmp_path / "wysiwyg" / "js" / "core.js").write_text("core", encoding="utf-8")

    result = READ_FILE.handler({"path": "./js/core.js"})

    assert result.ok is False
    assert result.error == "file_not_found"
    assert result.summary.index("wysiwyg/js/core.js") < result.summary.index("other/core.js")


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
    assert "Dossier :" in result.summary
    assert "a.py" in result.summary
    assert "sub" in result.summary


def test_list_dir_returns_paths_with_requested_prefix(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wysiwyg" / "js").mkdir(parents=True)
    (tmp_path / "wysiwyg" / "checks.html").write_text("", encoding="utf-8")

    result = LIST_DIR.handler({"path": "./wysiwyg"})

    assert result.ok is True
    assert "Dossier : wysiwyg" in result.summary
    assert "wysiwyg/checks.html" in result.summary
    assert "wysiwyg/js" in result.summary


def test_list_dir_hides_noise_dirs(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("", encoding="utf-8")

    result = LIST_DIR.handler({"path": str(tmp_path)})

    assert result.ok is True
    assert "app.py" in result.summary
    assert "__pycache__" not in result.summary
    assert ".git" not in result.summary


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


def test_make_dir_creates_nested_directory(tmp_path):
    dest = tmp_path / "a" / "b"

    result = MAKE_DIR.handler({"path": str(dest)})

    assert result.ok is True
    assert dest.is_dir()


def test_make_dir_missing_path_arg():
    result = MAKE_DIR.handler({})

    assert result.ok is False
    assert result.error == "missing_arg:path"


def test_move_path_moves_file(tmp_path):
    source = tmp_path / "source.txt"
    dest = tmp_path / "nested" / "dest.txt"
    source.write_text("hello", encoding="utf-8")

    result = MOVE_PATH.handler({"source": str(source), "destination": str(dest)})

    assert result.ok is True
    assert not source.exists()
    assert dest.read_text(encoding="utf-8") == "hello"


def test_move_path_refuses_existing_destination_without_overwrite(tmp_path):
    source = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    source.write_text("new", encoding="utf-8")
    dest.write_text("old", encoding="utf-8")

    result = MOVE_PATH.handler({"source": str(source), "destination": str(dest)})

    assert result.ok is False
    assert result.error == "destination_exists"
    assert source.exists()
    assert dest.read_text(encoding="utf-8") == "old"


def test_move_path_overwrites_when_requested(tmp_path):
    source = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    source.write_text("new", encoding="utf-8")
    dest.write_text("old", encoding="utf-8")

    result = MOVE_PATH.handler({"source": str(source), "destination": str(dest), "overwrite": True})

    assert result.ok is True
    assert not source.exists()
    assert dest.read_text(encoding="utf-8") == "new"
