"""Écriture des fichiers de corpus session pour le dreaming.

Brique standalone — dépend uniquement de la stdlib.
Répertoire par défaut : ~/.marius/sessions/

Format de fichier :
    YYYY-MM-DD-HHhMM.md
    ---
    project: <nom>
    cwd: <chemin absolu>
    opened_at: <ISO 8601>
    closed_at: <ISO 8601>
    turns: <entier>
    ---

Les fichiers session ne sont jamais injectés dans le contexte actif.
Ils sont lus par le dreaming puis archivés dans sessions/archive/.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"


@dataclass(frozen=True)
class SessionRecord:
    project: str
    cwd: str
    opened_at: str
    closed_at: str
    turns: int
    transcript: str = ""   # messages user + assistant (sans tool calls)


def write_session_file(
    record: SessionRecord,
    sessions_dir: Path | None = None,
) -> Path:
    """Écrit le fichier de corpus pour une session terminée.

    Le fichier contient les métadonnées en frontmatter YAML et le transcript
    de la conversation (user + assistant uniquement) dans le corps.

    Retourne le chemin du fichier créé.
    Silencieux en cas d'erreur — ne doit jamais bloquer la fermeture du REPL.
    """
    base = Path(sessions_dir) if sessions_dir else _MARIUS_HOME / "sessions"
    base.mkdir(parents=True, exist_ok=True)

    try:
        dt = datetime.fromisoformat(record.opened_at)
    except ValueError:
        dt = datetime.now(timezone.utc)

    filename = dt.strftime("%Y-%m-%d-%Hh%M.md")
    path = base / filename

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while path.exists():
        path = base / f"{stem}-{counter}{suffix}"
        counter += 1

    body = f"\n{record.transcript.strip()}\n" if record.transcript.strip() else ""
    content = (
        "---\n"
        f"project: {record.project}\n"
        f"cwd: {record.cwd}\n"
        f"opened_at: {record.opened_at}\n"
        f"closed_at: {record.closed_at}\n"
        f"turns: {record.turns}\n"
        f"---\n"
        f"{body}"
    )

    try:
        path.write_text(content, encoding="utf-8")
    except OSError:
        pass

    return path


def build_transcript(messages: list) -> str:
    """Construit un transcript lisible depuis une liste de Message.

    N'inclut que les rôles USER et ASSISTANT — pas les tool calls ni system.
    """
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "") or ""
        if role is None:
            continue
        role_name = role.value if hasattr(role, "value") else str(role)
        if role_name == "user":
            lines.append(f"**User** : {content.strip()}")
        elif role_name == "assistant" and content.strip():
            lines.append(f"**Assistant** : {content.strip()}")
    return "\n\n".join(lines)


def list_unprocessed(sessions_dir: Path | None = None) -> list[Path]:
    """Retourne les fichiers session non encore traités par le dreaming.

    Les fichiers traités sont dans sessions/archive/ — on exclut ce sous-dossier.
    """
    base = Path(sessions_dir) if sessions_dir else _MARIUS_HOME / "sessions"
    if not base.exists():
        return []
    return sorted(
        p for p in base.glob("*.md")
        if p.is_file()
    )


def archive_session_file(path: Path) -> Path:
    """Déplace un fichier session vers sessions/archive/ après traitement par le dreaming."""
    archive_dir = path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / path.name
    counter = 1
    while dest.exists():
        dest = archive_dir / f"{path.stem}-{counter}{path.suffix}"
        counter += 1
    path.rename(dest)
    return dest
