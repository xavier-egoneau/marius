from __future__ import annotations

from pathlib import Path

from marius.kernel.project_detector import ProjectSignal, detect_project


# ── signaux forts ─────────────────────────────────────────────────────────────


def test_git_repo_gives_strong_signal(tmp_path):
    (tmp_path / ".git").mkdir()
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG
    assert ".git" in result.markers_found


def test_pyproject_toml_gives_strong_signal(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG


def test_package_json_gives_strong_signal(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG


def test_cargo_toml_gives_strong_signal(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG


def test_go_mod_gives_strong_signal(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/foo")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG


def test_sln_extension_gives_strong_signal(tmp_path):
    (tmp_path / "MyApp.sln").write_text("")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG


# ── signaux modérés ───────────────────────────────────────────────────────────


def test_makefile_gives_moderate_signal(tmp_path):
    (tmp_path / "Makefile").write_text("all:")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.MODERATE
    assert "Makefile" in result.markers_found


def test_dockerfile_gives_moderate_signal(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM ubuntu")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.MODERATE


def test_requirements_txt_gives_moderate_signal(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.MODERATE


# ── signaux faibles ───────────────────────────────────────────────────────────


def test_readme_gives_weak_signal(tmp_path):
    (tmp_path / "README.md").write_text("# Mon projet")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.WEAK
    assert "README.md" in result.markers_found


def test_agents_md_gives_weak_signal(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Conventions")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.WEAK


# ── aucun marqueur ────────────────────────────────────────────────────────────


def test_empty_dir_gives_none_signal(tmp_path):
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.NONE
    assert result.markers_found == []


# ── chemins système refusés ───────────────────────────────────────────────────


def test_etc_is_denied():
    result = detect_project(Path("/etc"))
    assert result.signal is ProjectSignal.DENIED


def test_usr_bin_is_denied():
    result = detect_project(Path("/usr/bin"))
    assert result.signal is ProjectSignal.DENIED


def test_root_is_denied():
    result = detect_project(Path("/"))
    assert result.signal is ProjectSignal.DENIED


def test_home_dir_is_denied():
    result = detect_project(Path.home())
    assert result.signal is ProjectSignal.DENIED


def test_broad_home_documents_dir_is_denied():
    result = detect_project(Path.home() / "Documents")
    assert result.signal is ProjectSignal.DENIED


def test_shallow_path_is_denied():
    result = detect_project(Path("/home"))
    assert result.signal is ProjectSignal.DENIED


# ── is_project / is_denied helpers ───────────────────────────────────────────


def test_is_project_true_for_strong_signal(tmp_path):
    (tmp_path / ".git").mkdir()
    assert detect_project(tmp_path).is_project is True


def test_is_project_false_for_none_signal(tmp_path):
    assert detect_project(tmp_path).is_project is False


def test_is_denied_true_for_system_path():
    assert detect_project(Path("/etc")).is_denied is True


def test_is_denied_false_for_project(tmp_path):
    (tmp_path / ".git").mkdir()
    assert detect_project(tmp_path).is_denied is False


# ── strong prime sur modéré ───────────────────────────────────────────────────


def test_strong_marker_wins_over_moderate(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "Makefile").write_text("all:")
    result = detect_project(tmp_path)
    assert result.signal is ProjectSignal.STRONG
    assert ".git" in result.markers_found
