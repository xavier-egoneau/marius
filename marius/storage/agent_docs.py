"""Documents Markdown surchargeables par agent."""

from __future__ import annotations

import re
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"
_DOCS = {
    "soul": "SOUL.md",
    "identity": "IDENTITY.md",
    "user": "USER.md",
}
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def agent_doc_path(
    agent_name: str,
    name: str,
    *,
    marius_home: Path | None = None,
    workspace_root: Path | None = None,
) -> Path | None:
    filename = _DOCS.get(str(name or "").strip().lower())
    if not filename:
        return None
    if not _AGENT_NAME_RE.fullmatch(str(agent_name or "")):
        return None
    home = Path(marius_home) if marius_home is not None else _MARIUS_HOME
    root = Path(workspace_root) if workspace_root is not None else home / "workspace"
    try:
        resolved_root = root.resolve(strict=False)
        path = (resolved_root / agent_name / filename).resolve(strict=False)
        path.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return path


def global_doc_path(name: str, *, marius_home: Path | None = None) -> Path | None:
    filename = _DOCS.get(str(name or "").strip().lower())
    if not filename:
        return None
    home = Path(marius_home) if marius_home is not None else _MARIUS_HOME
    return home / filename


def seed_agent_docs_from_global(
    agent_name: str,
    *,
    marius_home: Path | None = None,
    workspace_root: Path | None = None,
) -> list[Path]:
    """Copie les docs globaux existants dans le workspace agent sans ecraser."""
    copied: list[Path] = []
    for key in _DOCS:
        source = global_doc_path(key, marius_home=marius_home)
        target = agent_doc_path(
            agent_name,
            key,
            marius_home=marius_home,
            workspace_root=workspace_root,
        )
        if source is None or target is None or not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        copied.append(target)
    return copied

