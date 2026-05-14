"""Collecte et structure du contexte d'entrée pour le dreaming et le daily."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from marius.kernel.skills import SkillReader
from marius.storage.memory_store import MemoryEntry, MemoryStore
from marius.storage.session_corpus import list_unprocessed


@dataclass
class DreamingContext:
    memories: list[MemoryEntry] = field(default_factory=list)
    session_summaries: list[str] = field(default_factory=list)  # métadonnées des sessions
    dream_contracts: list[tuple[str, str]] = field(default_factory=list)  # (skill, contenu)
    decisions_doc: str = ""
    roadmap_doc: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.memories and not self.dream_contracts


def build_dreaming_context(
    memory_store: MemoryStore,
    active_skills: list[str] | None = None,
    project_root: Path | None = None,
    sessions_dir: Path | None = None,
    skills_dir: Path | None = None,
) -> DreamingContext:
    """Collecte toutes les données d'entrée pour un cycle dreaming."""
    ctx = DreamingContext()

    # Mémoires courantes — tout le store, sans limite artificielle
    ctx.memories = memory_store.list(limit=2000)

    # Sessions non traitées
    for path in list_unprocessed(sessions_dir):
        ctx.session_summaries.append(_summarize_session_file(path))

    # Contrats des skills actifs
    if active_skills:
        reader = SkillReader(skills_dir)
        for skill in reader.load_all(active_skills):
            if skill.dream_content:
                ctx.dream_contracts.append((skill.meta.name, skill.dream_content))

    # Documents projet
    if project_root:
        ctx.decisions_doc = _read_optional(project_root / "DECISIONS.md")
        ctx.roadmap_doc   = _read_optional(project_root / "ROADMAP.md")

    return ctx


# ── helpers ───────────────────────────────────────────────────────────────────


def _read_optional(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _summarize_session_file(path: Path) -> str:
    """Extrait métadonnées + transcript d'un fichier session pour le dreaming."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Séparation frontmatter / corps
    parts = raw.split("---\n", 2)
    body = parts[2].strip() if len(parts) >= 3 else ""

    meta: dict[str, str] = {}
    if len(parts) >= 2:
        for line in parts[1].splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()

    project = meta.get("project", "?")
    opened  = meta.get("opened_at", "?")[:16].replace("T", " ")
    turns   = meta.get("turns", "?")

    header = f"### Session {opened}  projet={project}  tours={turns}"
    if body:
        return f"{header}\n{body}"
    return header
