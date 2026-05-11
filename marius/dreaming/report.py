"""Persistance du rapport de dream en JSON.

Chaque cycle dreaming produit un rapport sauvegardé dans
~/.marius/dreams/dream_<timestamp>.json.
Le daily lit le dernier rapport disponible sans relancer le dreaming.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"
_DREAMS_DIR  = _MARIUS_HOME / "dreams"


@dataclass
class DreamReport:
    generated_at: str
    added: int
    updated: int
    removed: int
    errors: int
    summary: str
    memories_count: int = 0
    sessions_count: int = 0
    skills: list[str] = field(default_factory=list)


def save_dream_report(
    report: DreamReport,
    dreams_dir: Path | None = None,
) -> Path:
    """Sauvegarde le rapport en JSON. Retourne le chemin du fichier."""
    base = Path(dreams_dir) if dreams_dir else _DREAMS_DIR
    base.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%Hh%M%S")
    path = base / f"dream_{ts}.json"
    try:
        path.write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return path


def load_last_dream_report(dreams_dir: Path | None = None) -> DreamReport | None:
    """Charge le rapport de dream le plus récent. Retourne None si aucun."""
    base = Path(dreams_dir) if dreams_dir else _DREAMS_DIR
    if not base.exists():
        return None
    files = sorted(base.glob("dream_*.json"), reverse=True)
    if not files:
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        return DreamReport(**{k: v for k, v in data.items() if k in DreamReport.__dataclass_fields__})
    except (OSError, json.JSONDecodeError, TypeError):
        return None
