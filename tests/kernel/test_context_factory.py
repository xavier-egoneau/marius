from __future__ import annotations

import json
from pathlib import Path

from marius.kernel.context_factory import build_system_prompt, needs_onboarding


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_system_prompt_does_not_onboard_without_assistant_skill(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "skills" / "onboarding" / "SKILL.md", "---\nname: onboarding\n---\nONBOARD")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=[],
        skills_dir=home / "skills",
        marius_home=home,
    )

    assert "âme" in prompt
    assert "Skill assistant inactif" in prompt
    assert "mode dev local" in prompt
    assert "prime sur le style général" in prompt
    assert "1 à 5 lignes" in prompt
    assert "Pas d'introduction" in prompt
    assert "ONBOARD" not in prompt
    assert "identity" not in loaded
    assert "user" not in loaded
    assert "onboarding" not in loaded


def test_build_system_prompt_loads_agent_dev_posture_without_assistant(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "agents" / "main" / "postures" / "dev.md", "Règle dev agent")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=[],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="main",
    )

    assert "Règle dev agent" in prompt
    assert "agent_posture_dev" in loaded


def test_build_system_prompt_loads_assistant_context_when_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "IDENTITY.md", "identité")
    _write(home / "USER.md", "profil")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=["assistant"],
        skills_dir=home / "skills",
        marius_home=home,
    )

    assert "identité" in prompt
    assert "profil" in prompt
    assert "Skill assistant actif" in prompt
    assert "identity" in loaded
    assert "user" in loaded
    assert "onboarding" not in loaded


def test_build_system_prompt_mentions_explicit_active_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "active_project.json", json.dumps({
        "path": str(project),
        "name": "projet-test",
        "set_at": "2026-05-15T10:00:00+00:00",
    }))

    prompt, _loaded = build_system_prompt(
        project,
        active_skills=[],
        skills_dir=home / "skills",
        marius_home=home,
    )

    assert "Projet actif explicite : projet-test" in prompt
    assert str(project) in prompt
    assert "project_set_active" in prompt


def test_build_system_prompt_prefers_agent_doc_over_global(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme globale")
    _write(home / "IDENTITY.md", "identité globale")
    _write(home / "USER.md", "profil global")
    _write(home / "workspace" / "main" / "SOUL.md", "âme agent")
    _write(home / "workspace" / "main" / "IDENTITY.md", "identité agent")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=["assistant"],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="main",
    )

    assert "âme agent" in prompt
    assert "âme globale" not in prompt
    assert "identité agent" in prompt
    assert "identité globale" not in prompt
    assert "profil global" in prompt
    assert "soul" in loaded
    assert "identity" in loaded
    assert "user" in loaded


def test_build_system_prompt_empty_agent_doc_masks_global(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme globale")
    _write(home / "workspace" / "main" / "SOUL.md", "")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=[],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="main",
    )

    assert "âme globale" not in prompt
    assert "soul" not in loaded


def test_build_system_prompt_loads_onboarding_only_for_assistant(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "skills" / "onboarding" / "SKILL.md", "---\nname: onboarding\n---\nONBOARD")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=["assistant"],
        skills_dir=home / "skills",
        marius_home=home,
    )

    assert "ONBOARD" in prompt
    assert "onboarding" in loaded


def test_build_system_prompt_uses_dev_posture_inside_assistant(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "agents" / "main" / "postures" / "dev.md", "Règle dev agent")
    _write(home / "skills" / "onboarding" / "SKILL.md", "---\nname: onboarding\n---\nONBOARD")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=["assistant"],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="main",
        dev_posture=True,
    )

    assert "posture dev projet active" in prompt
    assert "Règle dev agent" in prompt
    assert "agent_posture_dev" in loaded
    assert "chemins préfixés" in prompt
    assert "chemins exacts" in prompt
    assert "ONBOARD" not in prompt
    assert "onboarding" not in loaded


def test_build_system_prompt_does_not_load_agent_dev_posture_before_assistant_dev(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "IDENTITY.md", "identité")
    _write(home / "USER.md", "profil")
    _write(home / "agents" / "main" / "postures" / "dev.md", "Règle dev agent")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=["assistant"],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="main",
    )

    assert "Règle dev agent" not in prompt
    assert "agent_posture_dev" not in loaded


def test_build_system_prompt_ignores_unsafe_agent_name_for_posture(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    _write(home / "SOUL.md", "âme")
    _write(home / "postures" / "dev.md", "hors agents")

    prompt, loaded = build_system_prompt(
        project,
        active_skills=[],
        skills_dir=home / "skills",
        marius_home=home,
        agent_name="../..",
    )

    assert "hors agents" not in prompt
    assert "agent_posture_dev" not in loaded


def test_needs_onboarding_uses_given_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / "IDENTITY.md", "identité")
    _write(home / "USER.md", "profil")

    assert needs_onboarding(home) is False
