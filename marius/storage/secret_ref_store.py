"""Named secret references.

Stores references such as env:NAME or file:/path/token. It never stores secret
values and never returns resolved values.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARIUS_HOME = Path.home() / ".marius"
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


@dataclass
class SecretRef:
    name: str
    ref: str
    kind: str
    description: str
    created_at: str
    updated_at: str


class SecretRefStore:
    """Thread-safe JSON store for named secret references."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else _MARIUS_HOME / "secret_refs.json"
        self._lock = threading.Lock()

    def save(self, *, name: str, ref: str, description: str = "") -> SecretRef:
        name = name.strip()
        if not _NAME_RE.fullmatch(name):
            raise ValueError("invalid_secret_name")
        kind = secret_ref_kind(ref)
        if kind not in ("env", "file"):
            raise ValueError("invalid_secret_ref")
        now = _now()
        with self._lock:
            refs = self._load_raw()
            existing = next((item for item in refs if item.get("name") == name), None)
            if existing is None:
                existing = {"name": name, "created_at": now}
                refs.append(existing)
            existing.update({
                "ref": ref.strip(),
                "kind": kind,
                "description": description.strip(),
                "updated_at": now,
            })
            existing.setdefault("created_at", now)
            self._save_raw(refs)
            return _secret_from_raw(existing)

    def list(self) -> list[SecretRef]:
        with self._lock:
            raw = self._load_raw()
        refs = [_secret_from_raw(item) for item in raw]
        return sorted(refs, key=lambda item: item.name)

    def get(self, name: str) -> SecretRef | None:
        with self._lock:
            raw = self._load_raw()
        for item in raw:
            if item.get("name") == name:
                return _secret_from_raw(item)
        return None

    def delete(self, name: str) -> bool:
        with self._lock:
            raw = self._load_raw()
            kept = [item for item in raw if item.get("name") != name]
            if len(kept) == len(raw):
                return False
            self._save_raw(kept)
            return True

    def _load_raw(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, refs: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(refs, indent=2, ensure_ascii=False), encoding="utf-8")


def secret_ref_kind(ref: str) -> str:
    text = ref.strip()
    if text.startswith("env:") and text[4:].strip():
        return "env"
    if text.startswith("file:") and text[5:].strip():
        return "file"
    return ""


def _secret_from_raw(raw: dict[str, Any]) -> SecretRef:
    return SecretRef(
        name=str(raw.get("name") or ""),
        ref=str(raw.get("ref") or ""),
        kind=str(raw.get("kind") or secret_ref_kind(str(raw.get("ref") or ""))),
        description=str(raw.get("description") or ""),
        created_at=str(raw.get("created_at") or ""),
        updated_at=str(raw.get("updated_at") or ""),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_secret_data(secret: SecretRef) -> dict[str, Any]:
    return {
        "name": secret.name,
        "kind": secret.kind,
        "ref": secret.ref,
        "description": secret.description,
        "created_at": secret.created_at,
        "updated_at": secret.updated_at,
    }
