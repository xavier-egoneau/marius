from __future__ import annotations

from marius.tools.explore import EXPLORE_GREP, EXPLORE_SUMMARY, EXPLORE_TREE


def test_explore_tree_returns_compact_tree(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / ".git").mkdir()

    result = EXPLORE_TREE.handler({"path": str(tmp_path), "depth": 2})

    assert result.ok is True
    assert "src/" in result.summary
    assert "app.py" in result.summary
    assert ".git" not in result.summary
    assert any(entry["path"] == "src/app.py" for entry in result.data["entries"])


def test_explore_tree_rejects_missing_path(tmp_path):
    result = EXPLORE_TREE.handler({"path": str(tmp_path / "missing")})

    assert result.ok is False
    assert result.error == "path_not_found"


def test_explore_grep_finds_literal_matches(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 'needle'\n", encoding="utf-8")
    (tmp_path / "src" / "app.txt").write_text("needle in text", encoding="utf-8")

    result = EXPLORE_GREP.handler({"path": str(tmp_path), "pattern": "NEEDLE", "file_pattern": "*.py"})

    assert result.ok is True
    assert len(result.data["matches"]) == 1
    assert result.data["matches"][0]["path"] == "src/app.py"
    assert result.data["matches"][0]["line"] == 2


def test_explore_grep_supports_regex(tmp_path):
    file_path = tmp_path / "app.py"
    file_path.write_text("class Demo:\n    pass\n", encoding="utf-8")

    result = EXPLORE_GREP.handler({"path": str(file_path), "pattern": r"class\s+Demo", "regex": True})

    assert result.ok is True
    assert result.data["matches"][0]["line"] == 1


def test_explore_grep_invalid_regex_returns_error(tmp_path):
    file_path = tmp_path / "app.py"
    file_path.write_text("x", encoding="utf-8")

    result = EXPLORE_GREP.handler({"path": str(file_path), "pattern": "[", "regex": True})

    assert result.ok is False
    assert result.error == "invalid_regex"


def test_explore_summary_reads_project_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\nrequires-python = '>=3.11'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "src").mkdir()

    result = EXPLORE_SUMMARY.handler({"path": str(tmp_path)})

    assert result.ok is True
    assert result.data["metadata"]["name"] == "demo"
    assert "pyproject.toml" in result.data["key_files"]
    assert "src/" in result.data["top_level"]
