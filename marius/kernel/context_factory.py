"""Assemblage du system prompt Marius.

Brique standalone — utilisée par le REPL et le gateway.
"""

from __future__ import annotations

from pathlib import Path

from .context_builder import ContextBuildInput, ContextBuilder, ContextSource
from .skills import SkillReader, format_skill_context

_MARIUS_HOME = Path.home() / ".marius"
_ONBOARDING_SKILL = _MARIUS_HOME / "skills" / "onboarding" / "SKILL.md"


class _FileReader:
    def read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError):
            return None


def needs_onboarding() -> bool:
    """True si IDENTITY.md ou USER.md est absent ou vide."""
    for filename in ("IDENTITY.md", "USER.md"):
        path = _MARIUS_HOME / filename
        if not path.exists():
            return True
        if not path.read_text(encoding="utf-8").strip():
            return True
    return False


def build_system_prompt(
    project_root: Path,
    active_skills: list[str] | None = None,
    skills_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """Assemble le system prompt en quatre couches :

    1. Sources globales ~/.marius/ : SOUL → IDENTITY → USER → AGENTS
    2. AGENTS.md projet/workspace si différent du global
    3. Skill onboarding si IDENTITY.md ou USER.md est absent/vide
    4. Skills actifs de l'agent

    Retourne (markdown_assemblé, clés_chargées).
    """
    sources: list[ContextSource] = [
        ContextSource(key="soul",     title="Identité philosophique",  path=_MARIUS_HOME / "SOUL.md",     required=False),
        ContextSource(key="identity", title="Identité opérationnelle", path=_MARIUS_HOME / "IDENTITY.md", required=False),
        ContextSource(key="user",     title="Profil utilisateur",      path=_MARIUS_HOME / "USER.md",     required=False),
        ContextSource(key="agents",   title="Conventions",             path=_MARIUS_HOME / "AGENTS.md",   required=False),
    ]

    project_agents = project_root / "AGENTS.md"
    global_agents  = _MARIUS_HOME / "AGENTS.md"
    if project_agents.exists() and project_agents.resolve() != global_agents.resolve():
        sources.append(ContextSource(
            key="agents_project",
            title="Conventions projet",
            path=project_agents,
            required=False,
        ))

    if needs_onboarding():
        sources.append(ContextSource(
            key="onboarding",
            title="Onboarding",
            path=_ONBOARDING_SKILL,
            required=False,
        ))

    builder = ContextBuilder(reader=_FileReader())
    bundle  = builder.build(ContextBuildInput(sources=sources))
    loaded_keys: list[str] = [s.key for s in bundle.loaded_sources]

    skill_keys: list[str] = []
    if active_skills:
        reader = SkillReader(skills_dir)
        skills = reader.load_all(active_skills)
        skill_context = format_skill_context(skills)
        if skill_context:
            markdown = f"{bundle.markdown}\n\n{skill_context}".strip()
            skill_keys = [s.meta.name for s in skills if s.content]
        else:
            markdown = bundle.markdown
    else:
        markdown = bundle.markdown

    return markdown, loaded_keys + skill_keys
