"""Persistent approval audit and remembered decisions.

Standalone JSON store. It stores sanitized tool arguments, never raw secret-like
values, and can remember an approval/denial by fingerprint for future checks.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARIUS_HOME = Path.home() / ".marius"
_SECRET_KEYS = ("token", "secret", "password", "api_key", "key")


@dataclass
class ApprovalRecord:
    id: str
    created_at: str
    fingerprint: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    mode: str
    cwd: str
    approved: bool
    remembered: bool = False
    decided_at: str = ""


class ApprovalStore:
    """Thread-safe JSON store for permission approval records."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else _MARIUS_HOME / "approvals.json"
        self._lock = threading.Lock()

    def record(
        self,
        *,
        fingerprint: str,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
        mode: str,
        cwd: str,
        approved: bool,
        remembered: bool = False,
    ) -> ApprovalRecord:
        now = _now()
        record = ApprovalRecord(
            id=_record_id(now, fingerprint),
            created_at=now,
            fingerprint=fingerprint,
            tool_name=tool_name,
            arguments=_sanitize(arguments),
            reason=reason,
            mode=mode,
            cwd=cwd,
            approved=bool(approved),
            remembered=bool(remembered),
            decided_at=now if remembered else "",
        )
        with self._lock:
            records = self._load_raw()
            records.append(asdict(record))
            self._save_raw(records)
        return record

    def list(self, *, limit: int = 50, remembered_only: bool = False) -> list[ApprovalRecord]:
        with self._lock:
            raw = self._load_raw()
        records = [_record_from_raw(item) for item in raw]
        if remembered_only:
            records = [record for record in records if record.remembered]
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records[: max(1, min(200, limit))]

    def get(self, record_id: str) -> ApprovalRecord | None:
        with self._lock:
            raw = self._load_raw()
        for item in raw:
            if item.get("id") == record_id:
                return _record_from_raw(item)
        return None

    def lookup(self, fingerprint: str) -> bool | None:
        """Return the latest remembered decision for fingerprint, if any."""
        with self._lock:
            raw = self._load_raw()
        for item in reversed(raw):
            if item.get("fingerprint") == fingerprint and bool(item.get("remembered", False)):
                return bool(item.get("approved", False))
        return None

    def decide(self, record_id: str, *, approved: bool, remember: bool = True) -> ApprovalRecord | None:
        now = _now()
        with self._lock:
            raw = self._load_raw()
            for item in raw:
                if item.get("id") == record_id:
                    item["approved"] = bool(approved)
                    item["remembered"] = bool(remember)
                    item["decided_at"] = now
                    self._save_raw(raw)
                    return _record_from_raw(item)
        return None

    def forget(self, record_id: str) -> ApprovalRecord | None:
        with self._lock:
            raw = self._load_raw()
            for item in raw:
                if item.get("id") == record_id:
                    item["remembered"] = False
                    self._save_raw(raw)
                    return _record_from_raw(item)
        return None

    def _load_raw(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, records: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def _record_from_raw(raw: dict[str, Any]) -> ApprovalRecord:
    return ApprovalRecord(
        id=str(raw.get("id") or ""),
        created_at=str(raw.get("created_at") or ""),
        fingerprint=str(raw.get("fingerprint") or ""),
        tool_name=str(raw.get("tool_name") or ""),
        arguments=dict(raw.get("arguments") or {}),
        reason=str(raw.get("reason") or ""),
        mode=str(raw.get("mode") or ""),
        cwd=str(raw.get("cwd") or ""),
        approved=bool(raw.get("approved", False)),
        remembered=bool(raw.get("remembered", False)),
        decided_at=str(raw.get("decided_at") or ""),
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(secret_key in key_text.lower() for secret_key in _SECRET_KEYS):
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_id(timestamp: str, fingerprint: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace("+00:00", "Z")
    compact = compact.replace(".", "")
    return f"{compact}_{fingerprint}"
