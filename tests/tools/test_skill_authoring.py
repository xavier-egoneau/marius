from __future__ import annotations

from marius.kernel.skills import SkillReader
from marius.tools.skill_authoring import make_skill_authoring_tools


def _tools(tmp_path):
    return make_skill_authoring_tools(tmp_path / "skills")


def test_skill_create_writes_markdown_first_skill(tmp_path):
    tools = _tools(tmp_path)

    result = tools["skill_create"].handler(
        {
            "name": "writing",
            "description": "Writing posture",
            "body": "Write clearly.",
            "commands": ["draft"],
            "include_dream": True,
            "include_daily": True,
        }
    )

    skill_dir = tmp_path / "skills" / "writing"
    assert result.ok is True
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "DREAM.md").exists()
    assert (skill_dir / "DAILY.md").exists()
    assert (skill_dir / "core" / "draft.md").exists()

    skill = SkillReader(tmp_path / "skills").load("writing")
    assert skill is not None
    assert skill.meta.description == "Writing posture"
    assert "draft" in skill.commands


def test_skill_create_rejects_path_like_name(tmp_path):
    result = _tools(tmp_path)["skill_create"].handler({"name": "../bad", "description": "Bad"})

    assert result.ok is False
    assert result.error == "invalid_skill_name"


def test_skill_create_refuses_existing_skill_without_overwrite(tmp_path):
    tool = _tools(tmp_path)["skill_create"]
    assert tool.handler({"name": "demo", "description": "Demo"}).ok is True

    result = tool.handler({"name": "demo", "description": "Demo again"})

    assert result.ok is False
    assert result.error == "skill_exists"


def test_skill_list_returns_skills_and_commands(tmp_path):
    tools = _tools(tmp_path)
    tools["skill_create"].handler(
        {
            "name": "demo",
            "description": "Demo skill",
            "commands": ["run"],
        }
    )

    result = tools["skill_list"].handler({})

    assert result.ok is True
    names = [skill["name"] for skill in result.data["skills"]]
    assert "demo" in names
    demo = next(skill for skill in result.data["skills"] if skill["name"] == "demo")
    assert demo["commands"] == ["run"]


def test_skill_reload_returns_snapshot(tmp_path):
    tools = _tools(tmp_path)
    tools["skill_create"].handler(
        {
            "name": "demo",
            "description": "Demo skill",
            "commands": ["run"],
        }
    )

    result = tools["skill_reload"].handler({})

    assert result.ok is True
    assert "demo" in result.data["skills"]
    assert result.data["commands"] == [
        {"name": "run", "description": "run", "skill": "demo"},
    ]
