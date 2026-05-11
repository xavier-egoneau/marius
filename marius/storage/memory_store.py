"""Stockage persistant des souvenirs utilisateur (SQLite + FTS5).

Brique standalone — dépend uniquement de la stdlib.
Chemin par défaut : ~/.marius/memory.db

Deux scopes :
  global  → faits durables cross-projet (profil user, notes agent)
  project → contexte d'un projet précis (injecté seulement quand ce projet est actif)
"""

from __future__ import annotations

import re as _re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"

_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    content      TEXT NOT NULL UNIQUE,
    scope        TEXT NOT NULL DEFAULT 'global',
    project_path TEXT,
    category     TEXT NOT NULL DEFAULT 'general',
    tags         TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_SUPPORT_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_scope    ON memories(scope);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(content, tags, content=memories, content_rowid=memory_id);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags)
        VALUES (new.memory_id, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
        VALUES ('delete', old.memory_id, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
        VALUES ('delete', old.memory_id, old.content, old.tags);
    INSERT INTO memories_fts(rowid, content, tags)
        VALUES (new.memory_id, new.content, new.tags);
END;
"""

# Colonnes ajoutées après la création initiale — migration sûre
_MIGRATIONS = [
    "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'global'",
    "ALTER TABLE memories ADD COLUMN project_path TEXT",
]


@dataclass(frozen=True)
class MemoryEntry:
    id: int
    content: str
    scope: str
    project_path: str | None
    category: str
    tags: str
    created_at: str


class MemoryStore:
    """SQLite+FTS5 pour les souvenirs de l'utilisateur.

    Thread-safe. Dédupliqué par contenu exact (UNIQUE constraint).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        path = Path(db_path).expanduser() if db_path else _MARIUS_HOME / "memory.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_TABLE_SCHEMA)
        # Migration sûre : ajoute les colonnes manquantes avant les index/triggers
        # qui les référencent, pour les DBs créées par les premières versions.
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(memories)").fetchall()}
        for stmt in _MIGRATIONS:
            col = stmt.split("ADD COLUMN")[1].split()[0]
            if col not in existing:
                self._conn.execute(stmt)
                existing.add(col)
        self._conn.executescript(_SUPPORT_SCHEMA)
        self._rebuild_fts()
        self._conn.commit()

    def _rebuild_fts(self) -> None:
        try:
            self._conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            pass

    # ── write ─────────────────────────────────────────────────────────────────

    def add(
        self,
        content: str,
        *,
        scope: str = "global",
        project_path: str | None = None,
        category: str = "general",
        tags: str = "",
    ) -> int:
        """Ajoute un souvenir. Retourne le memory_id (existant si doublon)."""
        with self._lock:
            content = content.strip()
            if not content:
                raise ValueError("content must not be empty")
            try:
                cur = self._conn.execute(
                    "INSERT INTO memories (content, scope, project_path, category, tags) VALUES (?, ?, ?, ?, ?)",
                    (content, scope, project_path, category, tags),
                )
                self._conn.commit()
                return int(cur.lastrowid)  # type: ignore[arg-type]
            except sqlite3.IntegrityError:
                row = self._conn.execute(
                    "SELECT memory_id FROM memories WHERE content = ?", (content,)
                ).fetchone()
                return int(row["memory_id"])

    def replace(self, old_text: str, new_content: str) -> bool:
        """Remplace l'entrée contenant old_text. Retourne True si trouvée."""
        with self._lock:
            old_text = old_text.strip()
            new_content = new_content.strip()
            if not old_text or not new_content:
                return False
            row = self._conn.execute(
                "SELECT memory_id FROM memories WHERE content LIKE ?",
                (f"%{old_text}%",),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute(
                "UPDATE memories SET content = ? WHERE memory_id = ?",
                (new_content, row["memory_id"]),
            )
            self._conn.commit()
            return True

    def remove(self, memory_id: int) -> bool:
        """Supprime par memory_id. Retourne True si le souvenir existait."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE memory_id = ?", (memory_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def remove_by_text(self, old_text: str) -> bool:
        """Supprime l'entrée contenant old_text. Retourne True si trouvée."""
        with self._lock:
            row = self._conn.execute(
                "SELECT memory_id FROM memories WHERE content LIKE ?",
                (f"%{old_text}%",),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM memories WHERE memory_id = ?", (row["memory_id"],))
            self._conn.commit()
            return True

    # ── read ──────────────────────────────────────────────────────────────────

    def get_active_context(self, cwd: Path) -> list[MemoryEntry]:
        """Retourne les souvenirs actifs pour la session courante.

        = scope global + scope project pour le projet en cours.
        Utilisé comme snapshot à l'ouverture de session.
        """
        project_path = str(cwd.expanduser().resolve())
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT memory_id, content, scope, project_path, category, tags, created_at
                FROM memories
                WHERE scope = 'global'
                   OR (scope = 'project' AND project_path = ?)
                ORDER BY scope DESC, created_at DESC
                """,
                (project_path,),
            ).fetchall()
        return [_to_entry(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        project_path: str | None = None,
        category: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Recherche FTS5 par pertinence décroissante."""
        with self._lock:
            query = _sanitize_fts_query(query)
            if not query:
                return []
            params: list = [query]
            clauses: list[str] = []
            if scope is not None:
                clauses.append("m.scope = ?")
                params.append(scope)
            if project_path is not None:
                clauses.append("m.project_path = ?")
                params.append(project_path)
            if category is not None:
                clauses.append("m.category = ?")
                params.append(category)
            where = ("AND " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)
            sql = f"""
                SELECT m.memory_id, m.content, m.scope, m.project_path,
                       m.category, m.tags, m.created_at
                FROM memories m
                JOIN memories_fts fts ON fts.rowid = m.memory_id
                WHERE memories_fts MATCH ?
                  {where}
                ORDER BY fts.rank
                LIMIT ?
                """
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []
            return [_to_entry(r) for r in rows]

    def get(self, memory_id: int) -> MemoryEntry | None:
        """Retourne un souvenir par identifiant, ou None."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT memory_id, content, scope, project_path, category, tags, created_at
                FROM memories
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
        return _to_entry(row) if row is not None else None

    def list(
        self,
        *,
        scope: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Retourne les souvenirs les plus récents en premier."""
        with self._lock:
            clauses: list[str] = []
            params: list = []
            if scope is not None:
                clauses.append("scope = ?")
                params.append(scope)
            if category is not None:
                clauses.append("category = ?")
                params.append(category)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)
            rows = self._conn.execute(
                f"""
                SELECT memory_id, content, scope, project_path, category, tags, created_at
                FROM memories
                {where}
                ORDER BY created_at DESC, memory_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [_to_entry(r) for r in rows]

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ── helpers ───────────────────────────────────────────────────────────────────

_TOKEN_RE = _re.compile(r'\w+', _re.UNICODE)


def _sanitize_fts_query(query: str) -> str:
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"' for t in tokens)


def _to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=int(row["memory_id"]),
        content=row["content"],
        scope=row["scope"],
        project_path=row["project_path"],
        category=row["category"],
        tags=row["tags"],
        created_at=row["created_at"],
    )
