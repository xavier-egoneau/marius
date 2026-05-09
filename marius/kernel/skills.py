"""Lecteur de skills Marius.

Brique standalone — dépend uniquement de la stdlib.

Un skill est un dossier autonome et portable.
Il ne doit jamais contenir de chemins absolus — toujours générique et relatif.

Structure d'un skill :
    <skills_dir>/<nom>/
        ├── SKILL.md      ← instructions + frontmatter YAML (requis)
        ├── DREAM.md      ← contrat données pour le dreaming (optionnel)
        ├── DAILY.md      ← contrat données pour le daily (optionnel)
        └── core/         ← fichiers additionnels + prompts des commandes (optionnel)
            ├── plan.md   ← prompt pour la commande /plan
            └── ...

Frontmatter SKILL.md :
    ---
    name: mon-skill
    description: Ce que fait ce skill
    version: 1.0.0           (optionnel)
    commands: plan, dev, commit   (optionnel — noms des commandes REPL)
    ---

Frontmatter core/<cmd>.md :
    ---
    description: Courte description affichée dans /help
    ---
    <prompt injecté avant l'entrée utilisateur quand la commande est invoquée>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", re.MULTILINE)

_MARIUS_HOME = Path.home() / ".marius"
_SYSTEM_SKILLS: dict[str, tuple[str, str]] = {
    "assistant": (
        "Bloc assistant durable : IDENTITY.md, USER.md et onboarding conditionnel "
        "(workspace/gateway/daily à venir).",
        "system",
    ),
}


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    skill_dir: Path
    skill_file: Path
    version: str = ""


@dataclass(frozen=True)
class SkillCommand:
    """Commande REPL déclarée par un skill."""
    name: str
    description: str
    prompt: str   # injecté avant l'entrée utilisateur lors de l'invocation
    skill_name: str = ""


@dataclass(frozen=True)
class Skill:
    meta: SkillMeta
    content: str                                    # corps de SKILL.md sans le frontmatter
    dream_content: str = ""                         # contenu de DREAM.md si présent
    daily_content: str = ""                         # contenu de DAILY.md si présent
    core_files: dict[str, str] = field(default_factory=dict)    # core/<nom> → contenu brut
    commands: dict[str, SkillCommand] = field(default_factory=dict)  # nom → commande


class SkillReader:
    """Découverte et chargement des skills depuis le répertoire skills."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._dir = Path(skills_dir) if skills_dir else _MARIUS_HOME / "skills"

    def list(self) -> list[SkillMeta]:
        """Scanne le répertoire et retourne les métadonnées de tous les skills."""
        metas: list[SkillMeta] = [
            SkillMeta(
                name=name,
                description=description,
                skill_dir=self._dir / name,
                skill_file=self._dir / name / "SKILL.md",
                version=version,
            )
            for name, (description, version) in sorted(_SYSTEM_SKILLS.items())
        ]

        if not self._dir.exists():
            return metas

        for skill_dir in sorted(self._dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = _parse_meta(skill_file, skill_dir)
            if meta is not None:
                metas = [m for m in metas if m.name != meta.name]
                metas.append(meta)
        return metas

    def load(self, name: str) -> Skill | None:
        """Charge un skill complet par nom. Retourne None si introuvable."""
        if name in _SYSTEM_SKILLS:
            description, version = _SYSTEM_SKILLS[name]
            skill_dir  = self._dir / name
            skill_file = skill_dir / "SKILL.md"
            meta = SkillMeta(
                name=name,
                description=description,
                skill_dir=skill_dir,
                skill_file=skill_file,
                version=version,
            )
            # Si un SKILL.md existe, on lit son contenu (surcharge le system skill)
            if skill_file.exists():
                return _load_skill(meta)
            return Skill(meta=meta, content="")
        skill_dir = self._dir / name
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return None
        meta = _parse_meta(skill_file, skill_dir)
        if meta is None:
            return None
        return _load_skill(meta)

    def load_all(self, names: list[str]) -> list[Skill]:
        """Charge plusieurs skills par nom. Ignore les skills introuvables."""
        result: list[Skill] = []
        for name in names:
            skill = self.load(name)
            if skill is not None:
                result.append(skill)
        return result

    def exists(self, name: str) -> bool:
        return name in _SYSTEM_SKILLS or (self._dir / name / "SKILL.md").exists()


# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Sépare le frontmatter YAML du corps. Retourne (meta_dict, body)."""
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    fm_block = m.group(1)
    body = raw[m.end():]
    meta: dict[str, str] = {}
    for match in _KV_RE.finditer(fm_block):
        key = match.group(1).strip()
        value = match.group(2).strip().strip('"').strip("'")
        meta[key] = value
    return meta, body


def _parse_meta(skill_file: Path, skill_dir: Path) -> SkillMeta | None:
    try:
        raw = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, _ = _parse_frontmatter(raw)
    name = fm.get("name") or skill_dir.name
    description = fm.get("description", "")
    version = fm.get("version", "")
    return SkillMeta(
        name=name,
        description=description,
        skill_dir=skill_dir,
        skill_file=skill_file,
        version=version,
    )


def _load_skill(meta: SkillMeta) -> Skill:
    try:
        raw = meta.skill_file.read_text(encoding="utf-8")
    except OSError:
        return Skill(meta=meta, content="")
    fm, body = _parse_frontmatter(raw)

    dream_content = _read_optional(meta.skill_dir / "DREAM.md")
    daily_content = _read_optional(meta.skill_dir / "DAILY.md")
    core_files    = _read_core_dir(meta.skill_dir / "core")
    commands      = _parse_commands(fm, meta.skill_dir / "core", meta.name)

    return Skill(
        meta=meta,
        content=body.strip(),
        dream_content=dream_content,
        daily_content=daily_content,
        core_files=core_files,
        commands=commands,
    )


def _read_optional(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_core_dir(core_dir: Path) -> dict[str, str]:
    """Lit tous les fichiers du dossier core/ du skill. Retourne {nom: contenu}."""
    if not core_dir.is_dir():
        return {}
    files: dict[str, str] = {}
    for f in sorted(core_dir.iterdir()):
        if f.is_file():
            try:
                files[f.name] = f.read_text(encoding="utf-8").strip()
            except OSError:
                pass
    return files


def _parse_commands(
    fm: dict[str, str], core_dir: Path, skill_name: str
) -> dict[str, SkillCommand]:
    """Construit les commandes déclarées dans le frontmatter SKILL.md.

    Chaque commande listée dans `commands:` cherche son prompt dans
    core/<nom>.md. Si le fichier est absent, la commande est ignorée.
    """
    raw_cmds = fm.get("commands", "")
    cmd_names = [c.strip() for c in raw_cmds.split(",") if c.strip()]
    if not cmd_names:
        return {}

    commands: dict[str, SkillCommand] = {}
    for cmd_name in cmd_names:
        cmd_file = core_dir / f"{cmd_name}.md"
        if not cmd_file.exists():
            continue
        try:
            raw = cmd_file.read_text(encoding="utf-8")
        except OSError:
            continue
        cmd_fm, prompt_body = _parse_frontmatter(raw)
        description = cmd_fm.get("description", cmd_name)
        commands[cmd_name] = SkillCommand(
            name=cmd_name,
            description=description,
            prompt=prompt_body.strip(),
            skill_name=skill_name,
        )
    return commands


def collect_skill_commands(skills: list[Skill]) -> dict[str, SkillCommand]:
    """Agrège toutes les commandes de plusieurs skills. En cas de conflit, le dernier skill gagne."""
    commands: dict[str, SkillCommand] = {}
    for skill in skills:
        commands.update(skill.commands)
    return commands


def format_skill_context(skills: list[Skill]) -> str:
    """Formate les skills actifs pour injection dans le system prompt."""
    if not skills:
        return ""
    sections: list[str] = []
    for skill in skills:
        if skill.content:
            sections.append(f"## Skill : {skill.meta.name}\n{skill.content}")
    return "\n\n".join(sections)
