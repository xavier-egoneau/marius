"""SQLite store for Markdown RAG sources.

Standalone stdlib module. It persists source metadata, indexed Markdown
documents, and searchable chunks through FTS5.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marius.services.rag_markdown import MarkdownDocument, markdown_files, parse_markdown_file

_MARIUS_HOME = Path.home() / ".marius"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_sources (
    source_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'markdown',
    uri             TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'user',
    audience        TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL,
    path          TEXT NOT NULL,
    title         TEXT NOT NULL,
    checksum      TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at    TEXT NOT NULL,
    UNIQUE(source_id, path)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    source_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    importance  INTEGER NOT NULL DEFAULT 10,
    archived    INTEGER NOT NULL DEFAULT 0,
    line_start  INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_sources_scope ON rag_sources(scope);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_importance ON rag_chunks(importance);

CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts
    USING fts5(title, content, tags, content=rag_chunks, content_rowid=chunk_id);

CREATE TRIGGER IF NOT EXISTS rag_chunks_ai AFTER INSERT ON rag_chunks BEGIN
    INSERT INTO rag_chunks_fts(rowid, title, content, tags)
        VALUES (new.chunk_id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS rag_chunks_ad AFTER DELETE ON rag_chunks BEGIN
    INSERT INTO rag_chunks_fts(rag_chunks_fts, rowid, title, content, tags)
        VALUES ('delete', old.chunk_id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS rag_chunks_au AFTER UPDATE ON rag_chunks BEGIN
    INSERT INTO rag_chunks_fts(rag_chunks_fts, rowid, title, content, tags)
        VALUES ('delete', old.chunk_id, old.title, old.content, old.tags);
    INSERT INTO rag_chunks_fts(rowid, title, content, tags)
        VALUES (new.chunk_id, new.title, new.content, new.tags);
END;
"""


@dataclass(frozen=True)
class RagSource:
    id: str
    name: str
    kind: str
    uri: str
    scope: str
    audience: str
    tags: str
    enabled: bool
    created_at: str
    updated_at: str
    last_indexed_at: str | None


@dataclass(frozen=True)
class RagChunk:
    id: int
    document_id: int
    source_id: str
    source_name: str
    path: str
    title: str
    content: str
    tags: str
    importance: int
    archived: bool
    line_start: int
    created_at: str


@dataclass(frozen=True)
class RagDocumentSummary:
    path: str
    title: str
    chunk_count: int
    indexed_chunk_count: int
    tags: str
    checklist_open: int
    checklist_done: int
    bullet_count: int


@dataclass(frozen=True)
class RagDocumentHit:
    document_id: int
    source_id: str
    source_name: str
    path: str
    title: str
    tags: str
    checklist_open: int
    checklist_done: int
    bullet_count: int
    updated_at: str


@dataclass(frozen=True)
class RagSyncReport:
    source: RagSource
    files_seen: int
    documents_indexed: int
    chunks_indexed: int
    always_chunks: int
    important_chunks: int
    archived_chunks: int
    documents: list[RagDocumentSummary]
    errors: list[str]


class RagStore:
    def __init__(self, db_path: Path | None = None) -> None:
        path = Path(db_path).expanduser() if db_path else _MARIUS_HOME / "rag" / "rag.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._rebuild_fts()
        self._conn.commit()

    def _rebuild_fts(self) -> None:
        try:
            self._conn.execute("INSERT INTO rag_chunks_fts(rag_chunks_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            pass

    def add_source(
        self,
        *,
        name: str,
        uri: str,
        kind: str = "markdown",
        scope: str = "user",
        audience: str = "",
        tags: str = "",
        source_id: str | None = None,
        enabled: bool = True,
    ) -> RagSource:
        source_id = _slug(source_id or name)
        now = _now()
        with self._lock:
            existing = self.get_source(source_id)
            created_at = existing.created_at if existing else now
            self._conn.execute(
                """
                INSERT INTO rag_sources
                    (source_id, name, kind, uri, scope, audience, tags, enabled, created_at, updated_at, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    name=excluded.name,
                    kind=excluded.kind,
                    uri=excluded.uri,
                    scope=excluded.scope,
                    audience=excluded.audience,
                    tags=excluded.tags,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (source_id, name.strip(), kind, uri, scope, audience, tags, int(enabled), created_at, now, existing.last_indexed_at if existing else None),
            )
            self._conn.commit()
            source = self.get_source(source_id)
            assert source is not None
            return source

    def get_source(self, source_id: str) -> RagSource | None:
        row = self._conn.execute(
            "SELECT * FROM rag_sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        return _source(row) if row is not None else None

    def list_sources(self, *, include_disabled: bool = True) -> list[RagSource]:
        with self._lock:
            where = "" if include_disabled else "WHERE enabled = 1"
            rows = self._conn.execute(
                f"SELECT * FROM rag_sources {where} ORDER BY updated_at DESC, source_id"
            ).fetchall()
            return [_source(row) for row in rows]

    def sync_source(self, source_id: str) -> RagSyncReport:
        source = self.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        if source.kind != "markdown":
            raise ValueError(f"unsupported source kind: {source.kind}")

        root = Path(source.uri).expanduser()
        files = markdown_files(root)
        errors: list[str] = []
        documents: list[MarkdownDocument] = []
        for file in files:
            try:
                documents.append(parse_markdown_file(file))
            except OSError as exc:
                errors.append(f"{file}: {exc}")

        with self._lock:
            self._conn.execute(
                "DELETE FROM rag_chunks WHERE source_id = ?",
                (source.id,),
            )
            self._conn.execute(
                "DELETE FROM rag_documents WHERE source_id = ?",
                (source.id,),
            )
            chunks_indexed = 0
            always_chunks = 0
            important_chunks = 0
            archived_chunks = 0
            document_summaries: list[RagDocumentSummary] = []
            now = _now()
            for document in documents:
                content_hash = _checksum(document.path)
                document_tags: list[str] = []
                document_chunk_count = 0
                document_open = 0
                document_done = 0
                document_bullets = 0
                chunks_to_index = []
                for chunk in document.chunks:
                    document_chunk_count += 1
                    document_tags.extend(chunk.tags)
                    counts = _markdown_item_counts(chunk.content)
                    document_open += counts["checklist_open"]
                    document_done += counts["checklist_done"]
                    document_bullets += counts["bullet_count"]
                    if _should_index_chunk(chunk.tags):
                        chunks_to_index.append(chunk)
                merged_tags = _merge_tags(document_tags)
                metadata = dict(document.metadata)
                metadata["rag_inventory"] = {
                    "tags": merged_tags,
                    "chunk_count": document_chunk_count,
                    "indexed_chunk_count": len(chunks_to_index),
                    "checklist_open": document_open,
                    "checklist_done": document_done,
                    "bullet_count": document_bullets,
                }
                cur = self._conn.execute(
                    """
                    INSERT INTO rag_documents (source_id, path, title, checksum, metadata_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source.id,
                        str(document.path),
                        document.title,
                        content_hash,
                        json.dumps(metadata, ensure_ascii=False),
                        now,
                    ),
                )
                document_id = int(cur.lastrowid)
                for chunk in chunks_to_index:
                    tag_text = ",".join(chunk.tags)
                    self._conn.execute(
                        """
                        INSERT INTO rag_chunks
                            (document_id, source_id, title, content, tags, importance, archived, line_start, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            source.id,
                            chunk.title,
                            chunk.content,
                            tag_text,
                            chunk.importance,
                            int(chunk.archived),
                            chunk.line_start,
                            now,
                        ),
                    )
                    chunks_indexed += 1
                    tags = set(chunk.tags)
                    always_chunks += int("always" in tags)
                    important_chunks += int("important" in tags)
                    archived_chunks += int("archive" in tags)
                document_summaries.append(RagDocumentSummary(
                    path=str(document.path),
                    title=document.title,
                    chunk_count=document_chunk_count,
                    indexed_chunk_count=len(chunks_to_index),
                    tags=",".join(merged_tags),
                    checklist_open=document_open,
                    checklist_done=document_done,
                    bullet_count=document_bullets,
                ))
            self._conn.execute(
                "UPDATE rag_sources SET last_indexed_at = ?, updated_at = ? WHERE source_id = ?",
                (now, now, source.id),
            )
            self._conn.commit()

        refreshed = self.get_source(source.id)
        assert refreshed is not None
        return RagSyncReport(
            source=refreshed,
            files_seen=len(files),
            documents_indexed=len(documents),
            chunks_indexed=chunks_indexed,
            always_chunks=always_chunks,
            important_chunks=important_chunks,
            archived_chunks=archived_chunks,
            documents=document_summaries,
            errors=errors,
        )

    def search(
        self,
        query: str,
        *,
        source_id: str | None = None,
        scope: str | None = None,
        tag: str | None = None,
        include_archived: bool = False,
        limit: int = 10,
    ) -> list[RagChunk]:
        tokens = _query_tokens(query)
        fts_query = _sanitize_fts_tokens(tokens)
        if not fts_query:
            return []
        clauses, filter_params = _chunk_filters(
            source_id=source_id,
            scope=scope,
            tag=tag,
            include_archived=include_archived,
        )
        params: list[Any] = [fts_query, *filter_params, limit]
        where = " AND ".join(clauses)
        if where:
            where = f"AND {where}"
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT c.chunk_id, c.document_id, c.source_id, s.name AS source_name,
                       d.path, c.title, c.content, c.tags, c.importance,
                       c.archived, c.line_start, c.created_at
                FROM rag_chunks c
                JOIN rag_chunks_fts fts ON fts.rowid = c.chunk_id
                JOIN rag_sources s ON s.source_id = c.source_id
                JOIN rag_documents d ON d.document_id = c.document_id
                WHERE rag_chunks_fts MATCH ?
                  {where}
                ORDER BY c.importance DESC, fts.rank
                LIMIT ?
                """,
                params,
            ).fetchall()
            if rows:
                return [_chunk(row) for row in rows]
            return self._search_like_locked(
                tokens,
                source_id=source_id,
                scope=scope,
                tag=tag,
                include_archived=include_archived,
                limit=limit,
            )

    def _search_like_locked(
        self,
        tokens: list[str],
        *,
        source_id: str | None,
        scope: str | None,
        tag: str | None,
        include_archived: bool,
        limit: int,
    ) -> list[RagChunk]:
        clauses, params = _chunk_filters(
            source_id=source_id,
            scope=scope,
            tag=tag,
            include_archived=include_archived,
        )
        like_parts: list[str] = []
        for token in tokens:
            like_parts.append("(lower(c.title) LIKE ? OR lower(c.content) LIKE ? OR lower(c.tags) LIKE ? OR lower(d.path) LIKE ?)")
            needle = f"%{token.lower()}%"
            params.extend([needle, needle, needle, needle])
        if like_parts:
            clauses.append("(" + " OR ".join(like_parts) + ")")
        where = " AND ".join(clauses) if clauses else "1 = 1"
        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT c.chunk_id, c.document_id, c.source_id, s.name AS source_name,
                   d.path, c.title, c.content, c.tags, c.importance,
                   c.archived, c.line_start, c.created_at
            FROM rag_chunks c
            JOIN rag_sources s ON s.source_id = c.source_id
            JOIN rag_documents d ON d.document_id = c.document_id
            WHERE {where}
            ORDER BY c.importance DESC, c.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [_chunk(row) for row in rows]

    def search_documents(
        self,
        query: str,
        *,
        source_id: str | None = None,
        scope: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[RagDocumentHit]:
        tokens = _query_tokens(query)
        clauses: list[str] = []
        params: list[Any] = []
        if source_id:
            clauses.append("d.source_id = ?")
            params.append(source_id)
        if scope:
            clauses.append("s.scope = ?")
            params.append(scope)
        if tag:
            clauses.append("(lower(d.metadata_json) LIKE ?)")
            params.append(f"%{tag.strip().lower()}%")
        like_parts: list[str] = []
        for token in tokens:
            like_parts.append("(lower(d.title) LIKE ? OR lower(d.path) LIKE ? OR lower(d.metadata_json) LIKE ?)")
            needle = f"%{token.lower()}%"
            params.extend([needle, needle, needle])
        if like_parts:
            clauses.append("(" + " OR ".join(like_parts) + ")")
        where = " AND ".join(clauses) if clauses else "1 = 1"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT d.document_id, d.source_id, s.name AS source_name, d.path,
                       d.title, d.metadata_json, d.updated_at
                FROM rag_documents d
                JOIN rag_sources s ON s.source_id = d.source_id
                WHERE {where}
                ORDER BY d.updated_at DESC, d.path
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [_document_hit(row) for row in rows]

    def important(self, *, tag: str | None = None, limit: int = 20) -> list[RagChunk]:
        params: list[Any] = []
        clauses = ["c.archived = 0", "c.importance >= 55"]
        if tag:
            clauses.append("(',' || c.tags || ',') LIKE ?")
            params.append(f"%,{tag.strip().lower()},%")
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT c.chunk_id, c.document_id, c.source_id, s.name AS source_name,
                       d.path, c.title, c.content, c.tags, c.importance,
                       c.archived, c.line_start, c.created_at
                FROM rag_chunks c
                JOIN rag_sources s ON s.source_id = c.source_id
                JOIN rag_documents d ON d.document_id = c.document_id
                WHERE {' AND '.join(clauses)}
                ORDER BY c.importance DESC, c.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [_chunk(row) for row in rows]

    def get_chunk(self, chunk_id: int) -> RagChunk | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT c.chunk_id, c.document_id, c.source_id, s.name AS source_name,
                       d.path, c.title, c.content, c.tags, c.importance,
                       c.archived, c.line_start, c.created_at
                FROM rag_chunks c
                JOIN rag_sources s ON s.source_id = c.source_id
                JOIN rag_documents d ON d.document_id = c.document_id
                WHERE c.chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()
            return _chunk(row) if row is not None else None

    def close(self) -> None:
        self._conn.close()


def _chunk_filters(
    *,
    source_id: str | None,
    scope: str | None,
    tag: str | None,
    include_archived: bool,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if source_id:
        clauses.append("c.source_id = ?")
        params.append(source_id)
    if scope:
        clauses.append("s.scope = ?")
        params.append(scope)
    if tag:
        clauses.append("(',' || c.tags || ',') LIKE ?")
        params.append(f"%,{tag.strip().lower()},%")
    if not include_archived:
        clauses.append("c.archived = 0")
    return clauses, params


def _markdown_item_counts(content: str) -> dict[str, int]:
    checklist_open = 0
    checklist_done = 0
    bullet_count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r"^[-*]\s+\[[ xX]\]\s+", stripped):
            if "[ ]" in stripped:
                checklist_open += 1
            else:
                checklist_done += 1
            continue
        if re.match(r"^[-*]\s+\S+", stripped):
            bullet_count += 1
    return {
        "checklist_open": checklist_open,
        "checklist_done": checklist_done,
        "bullet_count": bullet_count,
    }


def _merge_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _should_index_chunk(tags: list[str]) -> bool:
    return bool({"always", "important", "routine", "fresh"} & set(tags))


_STOPWORDS = {
    "a", "ai", "au", "aux", "ce", "ces", "c", "d", "dans", "de", "des", "du",
    "en", "est", "j", "je", "la", "le", "les", "ma", "mes", "mon", "quoi",
    "que", "qui", "sur", "ta", "tes", "ton", "un", "une", "y",
}


def _query_tokens(query: str) -> list[str]:
    tokens = [
        token.lower()
        for token in _TOKEN_RE.findall(query)
        if len(token) >= 3 and token.lower() not in _STOPWORDS
    ]
    return tokens or [token.lower() for token in _TOKEN_RE.findall(query) if token]


def _sanitize_fts_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    return " OR ".join(f"{token}*" for token in tokens)


def _source(row: sqlite3.Row) -> RagSource:
    return RagSource(
        id=row["source_id"],
        name=row["name"],
        kind=row["kind"],
        uri=row["uri"],
        scope=row["scope"],
        audience=row["audience"],
        tags=row["tags"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_indexed_at=row["last_indexed_at"],
    )


def _chunk(row: sqlite3.Row) -> RagChunk:
    return RagChunk(
        id=int(row["chunk_id"]),
        document_id=int(row["document_id"]),
        source_id=row["source_id"],
        source_name=row["source_name"],
        path=row["path"],
        title=row["title"],
        content=row["content"],
        tags=row["tags"],
        importance=int(row["importance"]),
        archived=bool(row["archived"]),
        line_start=int(row["line_start"]),
        created_at=row["created_at"],
    )


def _document_hit(row: sqlite3.Row) -> RagDocumentHit:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        metadata = {}
    inventory = metadata.get("rag_inventory") if isinstance(metadata, dict) else {}
    if not isinstance(inventory, dict):
        inventory = {}
    tags = inventory.get("tags", [])
    if isinstance(tags, list):
        tag_text = ",".join(str(tag) for tag in tags)
    else:
        tag_text = str(tags or "")
    return RagDocumentHit(
        document_id=int(row["document_id"]),
        source_id=row["source_id"],
        source_name=row["source_name"],
        path=row["path"],
        title=row["title"],
        tags=tag_text,
        checklist_open=int(inventory.get("checklist_open") or 0),
        checklist_done=int(inventory.get("checklist_done") or 0),
        bullet_count=int(inventory.get("bullet_count") or 0),
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "source"


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def source_to_dict(source: RagSource) -> dict[str, Any]:
    return asdict(source)


def chunk_to_dict(chunk: RagChunk) -> dict[str, Any]:
    return asdict(chunk)


def document_hit_to_dict(document: RagDocumentHit) -> dict[str, Any]:
    return asdict(document)


def sync_report_to_dict(report: RagSyncReport) -> dict[str, Any]:
    data = asdict(report)
    data["source"] = source_to_dict(report.source)
    return data
