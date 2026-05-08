"""Tests du lecteur de skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.skills import Skill, SkillMeta, SkillReader, format_skill_context


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_skill(
    root: Path,
    name: str,
    *,
    description: str = "Un skill de test",
    version: str = "",
    body: str = "Instructions du skill.",
    dream: str | None = None,
    daily: str | None = None,
    core: dict[str, str] | None = None,
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [f"name: {name}", f"description: {description}"]
    if version:
        fm_lines.append(f"version: {version}")
    fm = "\n".join(fm_lines)
    (skill_dir / "SKILL.md").write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")
    if dream is not None:
        (skill_dir / "DREAM.md").write_text(dream, encoding="utf-8")
    if daily is not None:
        (skill_dir / "DAILY.md").write_text(daily, encoding="utf-8")
    if core:
        (skill_dir / "core").mkdir(exist_ok=True)
        for fname, content in core.items():
            (skill_dir / "core" / fname).write_text(content, encoding="utf-8")
    return skill_dir


# ── SkillReader.list ──────────────────────────────────────────────────────────


def test_list_empty_dir(tmp_path: Path) -> None:
    reader = SkillReader(tmp_path)
    metas = reader.list()
    assert [m.name for m in metas] == ["assistant"]


def test_list_nonexistent_dir(tmp_path: Path) -> None:
    reader = SkillReader(tmp_path / "nope")
    metas = reader.list()
    assert [m.name for m in metas] == ["assistant"]


def test_list_returns_skills(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", description="Dev skill")
    _make_skill(tmp_path, "writing", description="Writing skill")
    reader = SkillReader(tmp_path)
    metas = reader.list()
    assert len(metas) == 3
    names = {m.name for m in metas}
    assert names == {"assistant", "dev", "writing"}


def test_list_ignores_dirs_without_skill_md(tmp_path: Path) -> None:
    _make_skill(tmp_path, "good")
    (tmp_path / "empty_dir").mkdir()
    reader = SkillReader(tmp_path)
    assert {m.name for m in reader.list()} == {"assistant", "good"}


def test_list_ignores_files(tmp_path: Path) -> None:
    _make_skill(tmp_path, "good")
    (tmp_path / "not_a_dir.md").write_text("hello")
    reader = SkillReader(tmp_path)
    assert {m.name for m in reader.list()} == {"assistant", "good"}


def test_list_sorted_alphabetically(tmp_path: Path) -> None:
    _make_skill(tmp_path, "zebra")
    _make_skill(tmp_path, "alpha")
    _make_skill(tmp_path, "medium")
    reader = SkillReader(tmp_path)
    names = [m.name for m in reader.list()]
    assert names == ["assistant", "alpha", "medium", "zebra"]


# ── SkillReader.load ──────────────────────────────────────────────────────────


def test_load_not_found(tmp_path: Path) -> None:
    reader = SkillReader(tmp_path)
    assert reader.load("nope") is None


def test_load_system_assistant_skill(tmp_path: Path) -> None:
    reader = SkillReader(tmp_path)
    skill = reader.load("assistant")
    assert skill is not None
    assert skill.meta.name == "assistant"
    assert skill.content == ""


def test_load_basic(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", description="Dev skill", body="Aide le dev.")
    reader = SkillReader(tmp_path)
    skill = reader.load("dev")
    assert skill is not None
    assert skill.meta.name == "dev"
    assert skill.meta.description == "Dev skill"
    assert skill.content == "Aide le dev."
    assert skill.dream_content == ""
    assert skill.daily_content == ""
    assert skill.core_files == {}


def test_load_with_version(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", version="2.1.0")
    reader = SkillReader(tmp_path)
    skill = reader.load("dev")
    assert skill is not None
    assert skill.meta.version == "2.1.0"


def test_load_with_dream_and_daily(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", dream="Données pour le dreaming.", daily="Briefing daily.")
    reader = SkillReader(tmp_path)
    skill = reader.load("dev")
    assert skill is not None
    assert skill.dream_content == "Données pour le dreaming."
    assert skill.daily_content == "Briefing daily."


def test_load_with_core_files(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", core={"template.md": "# Template", "rules.txt": "Rule 1"})
    reader = SkillReader(tmp_path)
    skill = reader.load("dev")
    assert skill is not None
    assert "template.md" in skill.core_files
    assert skill.core_files["template.md"] == "# Template"
    assert skill.core_files["rules.txt"] == "Rule 1"


def test_load_name_fallback_to_dir_name(tmp_path: Path) -> None:
    """Si le frontmatter n'a pas de 'name', le nom du dossier est utilisé."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: Test\n---\nContenu.", encoding="utf-8")
    reader = SkillReader(tmp_path)
    skill = reader.load("my-skill")
    assert skill is not None
    assert skill.meta.name == "my-skill"


def test_load_no_frontmatter(tmp_path: Path) -> None:
    """SKILL.md sans frontmatter : contenu complet comme body."""
    skill_dir = tmp_path / "bare"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Contenu direct sans frontmatter.", encoding="utf-8")
    reader = SkillReader(tmp_path)
    skill = reader.load("bare")
    assert skill is not None
    assert "Contenu direct sans frontmatter." in skill.content


# ── SkillReader.load_all ──────────────────────────────────────────────────────


def test_load_all_ignores_missing(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev")
    reader = SkillReader(tmp_path)
    result = reader.load_all(["dev", "nope", "missing"])
    assert len(result) == 1
    assert result[0].meta.name == "dev"


def test_load_all_preserves_order(tmp_path: Path) -> None:
    _make_skill(tmp_path, "alpha")
    _make_skill(tmp_path, "beta")
    _make_skill(tmp_path, "gamma")
    reader = SkillReader(tmp_path)
    result = reader.load_all(["gamma", "alpha", "beta"])
    assert [s.meta.name for s in result] == ["gamma", "alpha", "beta"]


# ── SkillReader.exists ────────────────────────────────────────────────────────


def test_exists_true(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev")
    assert SkillReader(tmp_path).exists("dev") is True


def test_exists_false(tmp_path: Path) -> None:
    assert SkillReader(tmp_path).exists("dev") is False


def test_exists_system_assistant_skill(tmp_path: Path) -> None:
    assert SkillReader(tmp_path).exists("assistant") is True


# ── format_skill_context ──────────────────────────────────────────────────────


def test_format_empty(tmp_path: Path) -> None:
    assert format_skill_context([]) == ""


def test_format_single_skill(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", body="Aide le développement.")
    reader = SkillReader(tmp_path)
    skill = reader.load("dev")
    assert skill is not None
    result = format_skill_context([skill])
    assert "## Skill : dev" in result
    assert "Aide le développement." in result


def test_format_skips_empty_content(tmp_path: Path) -> None:
    skill_dir = tmp_path / "empty-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: empty-skill\ndescription: vide\n---\n", encoding="utf-8")
    reader = SkillReader(tmp_path)
    skill = reader.load("empty-skill")
    assert skill is not None
    result = format_skill_context([skill])
    assert result == ""


def test_format_multiple_skills(tmp_path: Path) -> None:
    _make_skill(tmp_path, "dev", body="Dev instructions.")
    _make_skill(tmp_path, "writing", body="Writing instructions.")
    reader = SkillReader(tmp_path)
    skills = reader.load_all(["dev", "writing"])
    result = format_skill_context(skills)
    assert "## Skill : dev" in result
    assert "## Skill : writing" in result
    assert result.index("dev") < result.index("writing")
