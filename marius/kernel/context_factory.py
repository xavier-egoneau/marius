"""Assemblage du system prompt Marius.

Brique standalone — utilisée par le REPL et le gateway.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from .context_builder import ContextBuildInput, ContextBuilder, ContextSource
from .posture import ASSISTANT_SKILL
from .skills import SkillReader, format_skill_context

_MARIUS_HOME = Path.home() / ".marius"


class _FileReader:
    def read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError):
            return None


def needs_onboarding(marius_home: Path | None = None) -> bool:
    """True si IDENTITY.md ou USER.md est absent ou vide."""
    home = Path(marius_home) if marius_home is not None else _MARIUS_HOME
    for filename in ("IDENTITY.md", "USER.md"):
        path = home / filename
        if not path.exists():
            return True
        if not path.read_text(encoding="utf-8").strip():
            return True
    return False


def _doc_path_with_agent_override(home: Path, filename: str, agent_name: str | None) -> Path:
    agent_path = _agent_workspace_doc_path(home, agent_name, filename)
    if agent_path is not None and agent_path.exists():
        return agent_path
    return home / filename


def _agent_workspace_doc_path(home: Path, agent_name: str | None, filename: str) -> Path | None:
    if not agent_name or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", agent_name):
        return None
    try:
        workspace_root = (home / "workspace").resolve(strict=False)
        path = (workspace_root / agent_name / filename).resolve(strict=False)
        path.relative_to(workspace_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return path


def build_system_prompt(
    project_root: Path,
    active_skills: list[str] | None = None,
    skills_dir: Path | None = None,
    marius_home: Path | None = None,
    agent_name: str | None = None,
    dev_posture: bool = False,
) -> tuple[str, list[str]]:
    """Assemble le system prompt en couches déclarées :

    1. Sources globales de base ~/.marius/ : SOUL → AGENTS
    2. AGENTS.md projet/workspace si différent du global
    3. Si skill `assistant` actif : IDENTITY → USER, puis onboarding si besoin hors posture dev
    4. Skills actifs de l'agent

    Retourne (markdown_assemblé, clés_chargées).
    """
    home = Path(marius_home) if marius_home is not None else _MARIUS_HOME
    assistant_enabled = ASSISTANT_SKILL in set(active_skills or [])
    dev_context_active = not assistant_enabled or dev_posture
    sources: list[ContextSource] = [
        ContextSource(
            key="soul",
            title="Identité philosophique",
            path=_doc_path_with_agent_override(home, "SOUL.md", agent_name),
            required=False,
        ),
        ContextSource(key="agents", title="Conventions",            path=home / "AGENTS.md", required=False),
    ]

    project_agents = project_root / "AGENTS.md"
    global_agents  = home / "AGENTS.md"
    if project_agents.exists() and project_agents.resolve() != global_agents.resolve():
        sources.append(ContextSource(
            key="agents_project",
            title="Conventions projet",
            path=project_agents,
            required=False,
        ))

    agent_dev_posture = _agent_posture_path(home, agent_name, "dev")
    if dev_context_active and agent_dev_posture is not None:
        sources.append(ContextSource(
            key="agent_posture_dev",
            title="Posture dev agent",
            path=agent_dev_posture,
            required=False,
        ))

    if assistant_enabled:
        sources.extend([
            ContextSource(
                key="identity",
                title="Identité opérationnelle",
                path=_doc_path_with_agent_override(home, "IDENTITY.md", agent_name),
                required=False,
            ),
            ContextSource(
                key="user",
                title="Profil utilisateur",
                path=_doc_path_with_agent_override(home, "USER.md", agent_name),
                required=False,
            ),
        ])

    onboarding_skill = home / "skills" / "onboarding" / "SKILL.md"
    if assistant_enabled and not dev_posture and _needs_onboarding_for_agent(home, agent_name):
        sources.append(ContextSource(
            key="onboarding",
            title="Onboarding",
            path=onboarding_skill,
            required=False,
        ))

    if assistant_enabled and dev_posture:
        preamble = (
            "## Capacités actives\n"
            "- Skill assistant actif, posture dev projet active.\n"
            "- Tu travailles sur le projet courant : privilégie lecture/édition/tests et résultats vérifiés.\n"
            "- Réponds court par défaut : 1 à 5 lignes, ou 3 à 5 puces maximum si une liste est utile.\n"
            "- Si un outil renvoie `file_not_found` ou `dir_not_found`, tiens compte des candidats proposés, "
            "liste le dossier parent, puis réessaie avec le chemin vérifié au lieu de répéter l'hypothèse.\n"
            "- Quand `list_dir` retourne des chemins préfixés, conserve ces chemins exacts dans tes prochaines lectures/écritures.\n"
            "- Pas d'onboarding, pas de profil durable, pas d'introduction ni conclusion décorative "
            "sauf demande explicite."
        )
    elif assistant_enabled:
        preamble = (
            "## Capacités actives\n"
            "- Skill assistant actif.\n"
            "- Agis d'abord, explique après. Quand l'utilisateur te demande de faire quelque chose, "
            "utilise les outils immédiatement — ne dis pas ce que tu vas faire, fais-le."
        )
    else:
        preamble = (
            "## Capacités actives\n"
            "- Skill assistant inactif : tu es en mode dev local.\n"
            "- Ne démarre pas d'onboarding, ne cherche pas IDENTITY.md ou USER.md, "
            "et réponds à la demande courante avec le contexte disponible.\n"
            "- Cette posture dev local prime sur le style général de SOUL.md.\n"
            "- Réponds court par défaut : 1 à 5 lignes, ou 3 à 5 puces maximum si une liste est utile.\n"
            "- Pas d'introduction, pas de reformulation de la demande, pas de conclusion décorative.\n"
            "- Privilégie uniquement les actions, constats utiles, chemins/fichiers, commandes et résultats vérifiés.\n"
            "- Si un outil renvoie `file_not_found` ou `dir_not_found`, tiens compte des candidats proposés, "
            "liste le dossier parent, puis réessaie avec le chemin vérifié au lieu de répéter l'hypothèse.\n"
            "- Quand `list_dir` retourne des chemins préfixés, conserve ces chemins exacts dans tes prochaines lectures/écritures.\n"
            "- Ne propose pas plusieurs suites possibles sauf si l'utilisateur demande explicitement des options.\n"
            "- N'ajoute pas de questions d'installation, de profil durable ou de conversation personnelle "
            "sauf si l'utilisateur les demande explicitement."
        )

    project_context = _project_context_hint(home)
    if project_context:
        preamble = f"{preamble}\n\n{project_context}"

    builder = ContextBuilder(reader=_FileReader())
    bundle  = builder.build(ContextBuildInput(preamble=preamble, sources=sources))
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


def _project_context_hint(home: Path) -> str:
    try:
        raw = json.loads((home / "active_project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        active = ""
        name = ""
    else:
        active = str(raw.get("path") or "").strip()
        name = str(raw.get("name") or "").strip()

    active_line = (
        f"- Projet actif explicite : {name or Path(active).name} ({active})."
        if active
        else "- Aucun projet actif explicite n'est défini."
    )
    return (
        "## Contexte projet explicite\n"
        f"{active_line}\n"
        "- Si l'utilisateur demande de travailler sur un projet connu différent du projet actif, "
        "utilise `project_list` pour lever l'ambiguïté puis `project_set_active` quand l'intention "
        "de basculer le travail est claire.\n"
        "- Si un autre projet est seulement cité comme comparaison, dépendance ou référence, "
        "ne change pas le projet actif sans confirmation."
    )


def _agent_posture_path(home: Path, agent_name: str | None, posture: str) -> Path | None:
    if not agent_name:
        return None
    try:
        agents_root = (home / "agents").resolve(strict=False)
        path = (agents_root / agent_name / "postures" / f"{posture}.md").resolve(strict=False)
        path.relative_to(agents_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return path


def _needs_onboarding_for_agent(home: Path, agent_name: str | None) -> bool:
    for filename in ("IDENTITY.md", "USER.md"):
        path = _doc_path_with_agent_override(home, filename, agent_name)
        if not path.exists():
            return True
        if not path.read_text(encoding="utf-8").strip():
            return True
    return False
