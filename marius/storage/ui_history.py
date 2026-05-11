"""Vue persistée de l'historique visible utilisateur.

Ce store est distinct du contexte interne compactable.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class VisibleHistoryEntry:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class InMemoryVisibleHistoryStore:
    """Store minimal pour l'historique visible, isolé par session."""

    def __init__(self) -> None:
        self._entries_by_session: dict[str, list[VisibleHistoryEntry]] = {}

    def append(self, session_id: str, entry: VisibleHistoryEntry) -> None:
        bucket = self._entries_by_session.setdefault(session_id, [])
        bucket.append(self._clone_entry(entry))

    def list_entries(self, session_id: str) -> list[VisibleHistoryEntry]:
        return [self._clone_entry(entry) for entry in self._entries_by_session.get(session_id, [])]

    @staticmethod
    def _clone_entry(entry: VisibleHistoryEntry) -> VisibleHistoryEntry:
        return replace(
            entry,
            metadata=deepcopy(entry.metadata),
            artifacts=deepcopy(entry.artifacts),
        )


class FileVisibleConversationStore:
    """Archive JSON de conversations visibles, indépendante du runtime LLM."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def archive(
        self,
        messages: list[dict[str, Any]],
        *,
        agent: str,
        opened_at: str | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_messages(messages)
        if not normalized:
            return None

        now = datetime.now(timezone.utc).isoformat()
        opened = opened_at or normalized[0].get("created_at") or now
        closed = closed_at or now
        conv_id = self._new_id(closed)
        record = {
            "id": conv_id,
            "agent": agent,
            "title": self._title(normalized),
            "opened_at": opened,
            "closed_at": closed,
            "turns": sum(1 for msg in normalized if msg.get("role") == "user"),
            "messages": normalized,
        }

        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / f"{conv_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._summary(record)

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self.base_dir.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.base_dir.glob("*.json"), reverse=True):
            record = self._read(path)
            if record is not None:
                records.append(self._summary(record))
            if len(records) >= limit:
                break
        return records

    def load(self, conversation_id: str) -> dict[str, Any] | None:
        safe_id = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        if not safe_id:
            return None
        path = self.base_dir / f"{safe_id}.json"
        record = self._read(path)
        if record is None:
            return None
        record["messages"] = self._normalize_messages(record.get("messages", []))
        return record

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({
                "role": role,
                "content": content,
                "created_at": str(item.get("created_at") or ""),
            })
        return normalized

    @staticmethod
    def _title(messages: list[dict[str, Any]]) -> str:
        first_user = next((msg["content"] for msg in messages if msg.get("role") == "user"), "")
        title = " ".join(first_user.split())
        if not title:
            return "Conversation"
        return title[:77] + "..." if len(title) > 80 else title

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(record.get("id") or ""),
            "agent": str(record.get("agent") or ""),
            "title": str(record.get("title") or "Conversation"),
            "opened_at": str(record.get("opened_at") or ""),
            "closed_at": str(record.get("closed_at") or ""),
            "turns": int(record.get("turns") or 0),
        }

    @staticmethod
    def _new_id(timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            dt = datetime.now(timezone.utc)
        return f"{dt.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
