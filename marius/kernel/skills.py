"""Lecteur de skills Marius.

Brique standalone — dépend uniquement de la stdlib.

Un skill est un dossier autonome et portable.
Il ne doit jamais contenir de chemins absolus — toujours générique et relatif.

Structure d'un skill :
    <skills_dir>/<nom>/
        ├── SKILL.md      ← instructions + frontmatter YAML (requis)
        ├── DREAM.md      ← contrat données pour le dreaming (optionnel)
        ├── DAILY.md      ← contrat données pour le daily (optionnel)
        └── core/         ← fichiers additionnels du skill (optionnel)

Localisation :
    - Mode local   : ~/.marius/skills/
    - Mode assistant : ~/.marius/workspace/<agent>/skills/  (futur)

Frontmatter SKILL.md :
    ---
    name: mon-skill
    description: Ce que fait ce skill
    version: 1.0.0       (optionnel)
    ---
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", re.MULTILINE)

_MARIUS_HOME = Path.home() / ".marius"


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    skill_dir: Path
    skill_file: Path
    version: str = ""


@dataclass(frozen=True)
class Skill:
    meta: SkillMeta
    content: str                          # corps de SKILL.md sans le frontmatter
    dream_content: str = ""               # contenu de DREAM.md si présent
    daily_content: str = ""               # contenu de DAILY.md si présent
    core_files: dict[str, str] = field(default_factory=dict)  # core/<nom> → contenu


class SkillReader:
    """Découverte et chargement des skills depuis le répertoire skills."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._dir = Path(skills_dir) if skills_dir else _MARIUS_HOME / "skills"

    def list(self) -> list[SkillMeta]:
        """Scanne le répertoire et retourne les métadonnées de tous les skills."""
        if not self._dir.exists():
            return []

        metas: list[SkillMeta] = []
        for skill_dir in sorted(self._dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = _parse_meta(skill_file, skill_dir)
            if meta is not None:
                metas.append(meta)
        return metas

    def load(self, name: str) -> Skill | None:
        """Charge un skill complet par nom. Retourne None si introuvable."""
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
        return (self._dir / name / "SKILL.md").exists()


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
    _, body = _parse_frontmatter(raw)

    dream_content = _read_optional(meta.skill_dir / "DREAM.md")
    daily_content = _read_optional(meta.skill_dir / "DAILY.md")
    core_files    = _read_core_dir(meta.skill_dir / "core")

    return Skill(
        meta=meta,
        content=body.strip(),
        dream_content=dream_content,
        daily_content=daily_content,
        core_files=core_files,
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


def format_skill_context(skills: list[Skill]) -> str:
    """Formate les skills actifs pour injection dans le system prompt."""
    if not skills:
        return ""
    sections: list[str] = []
    for skill in skills:
        if skill.content:
            sections.append(f"## Skill : {skill.meta.name}\n{skill.content}")
    return "\n\n".join(sections)
