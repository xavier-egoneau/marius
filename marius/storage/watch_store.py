"""Persistent watch topics for Marius.

Standalone JSON storage. It does not perform network calls; tools decide how to
run a topic and store reports here.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARIUS_HOME = Path.home() / ".marius"
DEFAULT_WATCH_DIR = _MARIUS_HOME / "watch"
DEFAULT_TOPICS_PATH = DEFAULT_WATCH_DIR / "topics.json"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")


@dataclass(frozen=True)
class WatchTopic:
    id: str
    title: str
    query: str
    cadence: str = "manual"
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run_at: str = ""
    tags: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WatchReport:
    id: str
    topic_id: str
    title: str
    query: str
    generated_at: str
    results: list[dict[str, Any]]
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class WatchStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_WATCH_DIR
        self.topics_path = self.root / "topics.json"
        self.reports_dir = self.root / "reports"

    def list_topics(self, *, include_disabled: bool = True) -> list[WatchTopic]:
        topics = self._load_topics()
        if not include_disabled:
            topics = [topic for topic in topics if topic.enabled]
        return sorted(topics, key=lambda topic: topic.title.lower())

    def get(self, topic_id: str) -> WatchTopic | None:
        return next((topic for topic in self._load_topics() if topic.id == topic_id), None)

    def add(
        self,
        *,
        title: str,
        query: str,
        cadence: str = "manual",
        tags: list[str] | None = None,
        settings: dict[str, Any] | None = None,
        topic_id: str | None = None,
    ) -> WatchTopic:
        topics = self._load_topics()
        new_id = _valid_id(topic_id) if topic_id else _unique_id(title, topics)
        now = datetime.now(timezone.utc).isoformat()
        existing = next((topic for topic in topics if topic.id == new_id), None)
        topic = WatchTopic(
            id=new_id,
            title=title,
            query=query,
            cadence=cadence or "manual",
            enabled=True,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_run_at=existing.last_run_at if existing else "",
            tags=list(tags or []),
            settings=_merged_settings(existing.settings if existing else {}, settings),
        )
        topics = [topic if old.id == new_id else old for old in topics]
        if existing is None:
            topics.append(topic)
        self._save_topics(topics)
        return topic

    def remove(self, topic_id: str) -> bool:
        topics = self._load_topics()
        remaining = [topic for topic in topics if topic.id != topic_id]
        if len(remaining) == len(topics):
            return False
        self._save_topics(remaining)
        return True

    def set_enabled(self, topic_id: str, enabled: bool) -> bool:
        topics = self._load_topics()
        changed = False
        now = datetime.now(timezone.utc).isoformat()
        updated: list[WatchTopic] = []
        for topic in topics:
            if topic.id == topic_id:
                updated.append(WatchTopic(**{**asdict(topic), "enabled": enabled, "updated_at": now}))
                changed = True
            else:
                updated.append(topic)
        if changed:
            self._save_topics(updated)
        return changed

    def save_report(
        self,
        topic: WatchTopic,
        results: list[dict[str, Any]],
        *,
        summary: str = "",
        dedupe: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> WatchReport:
        now = datetime.now(timezone.utc)
        original_count = len(results)
        duplicate_count = 0
        if dedupe:
            results, duplicate_count = self.dedupe_results(topic.id, results)
            duplicate_count = original_count - len(results)
            if duplicate_count:
                suffix = f"{duplicate_count} duplicate result(s) skipped"
                summary = f"{summary}; {suffix}" if summary else suffix
        report_metadata = dict(metadata or {})
        report_metadata.setdefault("duplicate_count", duplicate_count)
        report_metadata.update(_result_metrics(results))
        report_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{topic.id}_{uuid.uuid4().hex[:6]}"
        report = WatchReport(
            id=report_id,
            topic_id=topic.id,
            title=topic.title,
            query=topic.query,
            generated_at=now.isoformat(),
            results=results,
            summary=summary,
            metadata=report_metadata,
        )
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / f"{report_id}.json").write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._mark_run(topic.id, report.generated_at)
        return report

    def list_reports(self, *, limit: int = 20) -> list[WatchReport]:
        if limit <= 0 or not self.reports_dir.exists():
            return []
        reports: list[WatchReport] = []
        for path in self.reports_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                reports.append(_report_from_dict(raw))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
        reports.sort(key=lambda report: (report.generated_at, report.id), reverse=True)
        return reports[:limit]

    def last_seen_urls(self, topic_id: str, *, limit: int = 20) -> set[str]:
        urls: set[str] = set()
        for report in self.list_reports(limit=limit):
            if report.topic_id != topic_id:
                continue
            for result in report.results:
                url = str(result.get("url") or "").strip()
                if url:
                    urls.add(url)
        return urls

    def dedupe_results(self, topic_id: str, results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen = self.last_seen_urls(topic_id)
        filtered: list[dict[str, Any]] = []
        duplicate_count = 0
        for result in results:
            url = str(result.get("url") or "").strip()
            if url and url in seen:
                duplicate_count += 1
                continue
            if url:
                seen.add(url)
            filtered.append(result)
        return filtered, duplicate_count

    def _mark_run(self, topic_id: str, timestamp: str) -> None:
        topics = self._load_topics()
        updated = [
            WatchTopic(**{**asdict(topic), "last_run_at": timestamp, "updated_at": timestamp})
            if topic.id == topic_id else topic
            for topic in topics
        ]
        self._save_topics(updated)

    def _dedupe_results(self, topic_id: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered, _duplicate_count = self.dedupe_results(topic_id, results)
        return filtered

    def _load_topics(self) -> list[WatchTopic]:
        if not self.topics_path.exists():
            return []
        try:
            raw = json.loads(self.topics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = raw.get("topics", []) if isinstance(raw, dict) else []
        topics: list[WatchTopic] = []
        for item in items:
            try:
                topics.append(_topic_from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return topics

    def _save_topics(self, topics: list[WatchTopic]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.topics_path.write_text(
            json.dumps({"topics": [asdict(topic) for topic in topics]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _topic_from_dict(raw: dict[str, Any]) -> WatchTopic:
    return WatchTopic(
        id=str(raw["id"]),
        title=str(raw["title"]),
        query=str(raw["query"]),
        cadence=str(raw.get("cadence") or "manual"),
        enabled=bool(raw.get("enabled", True)),
        created_at=str(raw.get("created_at") or ""),
        updated_at=str(raw.get("updated_at") or ""),
        last_run_at=str(raw.get("last_run_at") or ""),
        tags=[str(tag) for tag in raw.get("tags", []) if str(tag).strip()],
        settings=_dict(raw.get("settings")),
    )


def _report_from_dict(raw: dict[str, Any]) -> WatchReport:
    results = raw.get("results", [])
    if not isinstance(results, list):
        results = []
    return WatchReport(
        id=str(raw["id"]),
        topic_id=str(raw["topic_id"]),
        title=str(raw.get("title") or ""),
        query=str(raw.get("query") or ""),
        generated_at=str(raw.get("generated_at") or ""),
        results=[item for item in results if isinstance(item, dict)],
        summary=str(raw.get("summary") or ""),
        metadata=_dict(raw.get("metadata")),
    )


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _merged_settings(existing: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    if incoming is None:
        return dict(existing)
    merged = dict(existing)
    for key, value in incoming.items():
        if value is not None:
            merged[str(key)] = value
    return merged


def _result_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [_float(item.get("novelty_score")) for item in results]
    scores = [score for score in scores if score is not None]
    new_count = sum(1 for item in results if bool(item.get("is_new", False)))
    return {
        "result_count": len(results),
        "new_count": new_count,
        "max_novelty_score": max(scores) if scores else 0.0,
        "average_novelty_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
    }


def _float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_id(title: str, topics: list[WatchTopic]) -> str:
    base = re.sub(r"[^a-z0-9_-]+", "-", title.lower()).strip("-_")[:48] or "topic"
    existing = {topic.id for topic in topics}
    if base not in existing:
        return base
    for idx in range(2, 1000):
        candidate = f"{base}-{idx}"
        if candidate not in existing:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _valid_id(value: str | None) -> str:
    topic_id = str(value or "").strip()
    if not _ID_RE.fullmatch(topic_id):
        raise ValueError("Invalid topic id. Use lowercase letters, digits, '-' or '_'.")
    return topic_id
