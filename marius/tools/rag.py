"""Markdown RAG tools.

The tools manage sources and return observations. They never replace the
assistant's final answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.memory_store import MemoryStore
from marius.storage.rag_store import (
    RagChunk,
    RagSource,
    RagStore,
    chunk_to_dict,
    document_hit_to_dict,
    source_to_dict,
    sync_report_to_dict,
)

_DEFAULT_ROOT = Path.home() / ".marius" / "workspace" / "main" / "skills" / "rag"
_SCOPES = {"org", "group", "project", "user"}


def make_rag_tools(
    root: Path | None = None,
    *,
    memory_store: MemoryStore | None = None,
    cwd: Path | None = None,
) -> dict[str, ToolEntry]:
    base = Path(root) if root is not None else _DEFAULT_ROOT
    store = RagStore(base / "rag.db")
    project_root = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()

    def source_add(arguments: dict[str, Any]) -> ToolResult:
        name = _text(arguments.get("name"))
        uri = _text(arguments.get("path") or arguments.get("uri"))
        kind = _text(arguments.get("kind")) or "markdown"
        scope = (_text(arguments.get("scope")) or "user").lower()
        audience = _text(arguments.get("audience"))
        tags = ",".join(_string_list(arguments.get("tags")))
        source_id = _text(arguments.get("source_id")) or None
        if not name:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `name` missing.", error="missing_arg:name")
        if not uri:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `path` or `uri` missing.", error="missing_arg:uri")
        if kind != "markdown":
            return ToolResult(tool_call_id="", ok=False, summary="Only `markdown` sources are supported in RAG v1.", error="unsupported_kind")
        if scope not in _SCOPES:
            return ToolResult(tool_call_id="", ok=False, summary=f"Invalid scope: {scope}.", error="invalid_scope")
        path = Path(uri).expanduser()
        if not path.exists():
            return ToolResult(tool_call_id="", ok=False, summary=f"Source path not found: {path}", error="path_not_found")
        source = store.add_source(
            name=name,
            uri=str(path.resolve()),
            kind=kind,
            scope=scope,
            audience=audience,
            tags=tags,
            source_id=source_id,
            enabled=bool(arguments.get("enabled", True)),
        )
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"RAG source saved: {source.id} — {source.name}",
            data={"source": source_to_dict(source)},
        )

    def source_list(arguments: dict[str, Any]) -> ToolResult:
        include_disabled = bool(arguments.get("include_disabled", True))
        sources = store.list_sources(include_disabled=include_disabled)
        lines = [f"RAG sources: {len(sources)} source(s)."]
        for source in sources:
            status = "enabled" if source.enabled else "disabled"
            indexed = f", indexed {source.last_indexed_at[:16]}" if source.last_indexed_at else ""
            lines.append(f"- {source.id}: {source.name} ({source.scope}, {status}{indexed})")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={"sources": [source_to_dict(source) for source in sources]},
        )

    def source_sync(arguments: dict[str, Any]) -> ToolResult:
        source_id = _text(arguments.get("source_id"))
        sources = [store.get_source(source_id)] if source_id else store.list_sources(include_disabled=False)
        sources = [source for source in sources if source is not None and source.enabled]
        if not sources:
            return ToolResult(tool_call_id="", ok=False, summary="No enabled RAG source to sync.", error="no_source")
        reports = []
        lines = [f"RAG sync: {len(sources)} source(s)."]
        for source in sources:
            try:
                report = store.sync_source(source.id)
            except (KeyError, ValueError) as exc:
                lines.append(f"- {source.id}: failed — {exc}")
                reports.append({"source": source_to_dict(source), "ok": False, "error": str(exc)})
                continue
            lines.append(
                f"- {source.id}: {report.documents_indexed} document(s) catalogued, "
                f"{report.chunks_indexed} tagged chunk(s) indexed, "
                f"{report.always_chunks} [always], {report.important_chunks} [important]"
            )
            for document in report.documents[:12]:
                lines.append(f"  - {_document_summary_line(document, source)}")
            if len(report.documents) > 12:
                lines.append(f"  - ... {len(report.documents) - 12} other document(s)")
            reports.append({"ok": True, "report": sync_report_to_dict(report)})
        return ToolResult(
            tool_call_id="",
            ok=any(item.get("ok") for item in reports),
            summary="\n".join(lines),
            data={"reports": reports},
        )

    def search(arguments: dict[str, Any]) -> ToolResult:
        query = _text(arguments.get("query"))
        limit = _bounded_int(arguments.get("limit"), default=8, minimum=1, maximum=30)
        tag = _text(arguments.get("tag")) or None
        source_id = _text(arguments.get("source_id")) or None
        scope = _text(arguments.get("scope")) or None
        include_archived = bool(arguments.get("include_archived", False))
        if query:
            chunks = store.search(
                query,
                source_id=source_id,
                scope=scope,
                tag=tag,
                include_archived=include_archived,
                limit=limit,
            )
            documents = []
            if not chunks:
                documents = store.search_documents(
                    query,
                    source_id=source_id,
                    scope=scope,
                    tag=tag,
                    limit=limit,
                )
            title = f"RAG search `{query}`"
        else:
            chunks = store.important(tag=tag, limit=limit)
            documents = []
            title = "RAG important chunks"
        return _search_result(chunks, documents, title)

    def get(arguments: dict[str, Any]) -> ToolResult:
        chunk_id = arguments.get("chunk_id")
        if not isinstance(chunk_id, int):
            return ToolResult(tool_call_id="", ok=False, summary="Integer `chunk_id` missing.", error="missing_arg:chunk_id")
        chunk = store.get_chunk(chunk_id)
        if chunk is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"RAG chunk not found: {chunk_id}", error="chunk_not_found")
        return _chunks_result([chunk], "RAG chunk")

    def promote_to_memory(arguments: dict[str, Any]) -> ToolResult:
        if memory_store is None:
            return ToolResult(tool_call_id="", ok=False, summary="Memory store unavailable.", error="memory_unavailable")
        chunk_id = arguments.get("chunk_id")
        content = _text(arguments.get("content"))
        if isinstance(chunk_id, int):
            chunk = store.get_chunk(chunk_id)
            if chunk is None:
                return ToolResult(tool_call_id="", ok=False, summary=f"RAG chunk not found: {chunk_id}", error="chunk_not_found")
            content = _text(arguments.get("content")) or _memory_content(chunk)
            tags = f"rag,{chunk.tags}".strip(",")
        else:
            chunk = None
            tags = "rag"
        if not content:
            return ToolResult(tool_call_id="", ok=False, summary="`chunk_id` or `content` required.", error="missing_content")
        scope = (_text(arguments.get("memory_scope")) or "global").lower()
        project_path = str(project_root) if scope == "project" else None
        memory_id = memory_store.add(
            content,
            scope=scope if scope in ("global", "project") else "global",
            project_path=project_path,
            category="rag",
            tags=tags,
        )
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"RAG entry promoted to memory #{memory_id}.",
            data={"memory_id": memory_id, "chunk": chunk_to_dict(chunk) if chunk else None},
        )

    def checklist_add(arguments: dict[str, Any]) -> ToolResult:
        items = _string_list(arguments.get("items"), preserve_case=True)
        if not items:
            item = _text(arguments.get("item"))
            items = [item] if item else []
        if not items:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `item` or `items` missing.", error="missing_arg:item")
        path_text = _text(arguments.get("path"))
        source_id = _text(arguments.get("source_id"))
        list_name = _text(arguments.get("list_name")) or "todo"
        source = store.get_source(source_id) if source_id else None
        path = _resolve_checklist_path(path_text, list_name=list_name, source=source, base=base)
        path.parent.mkdir(parents=True, exist_ok=True)
        title = _title_from_path(path, list_name)
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# {title}\n\n"
        lines = existing.splitlines()
        if not lines:
            lines = [f"# {title}", ""]
        elif not lines[0].lstrip().startswith("#"):
            lines = [f"# {title}", "", *lines]

        existing_items = {_normalize_item(line) for line in lines if _is_checklist_line(line)}
        added: list[str] = []
        for item in items:
            normalized = _normalize_text(item)
            if not normalized or normalized in existing_items:
                continue
            if lines and lines[-1].strip():
                pass
            lines.append(f"- [ ] {item.strip()}")
            existing_items.add(normalized)
            added.append(item.strip())
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        synced = None
        if source is not None:
            try:
                synced = sync_report_to_dict(store.sync_source(source.id))
            except (KeyError, ValueError, OSError):
                synced = None
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"{len(added)} checklist item(s) added to `{path.name}`.",
            data={"path": str(path), "added": added, "source": source_to_dict(source) if source else None, "sync": synced},
            artifacts=[Artifact(type=ArtifactType.FILE, path=str(path))],
        )

    return {
        "rag_source_add": ToolEntry(
            ToolDefinition(
                name="rag_source_add",
                description="Register or update a local Markdown RAG source. The assistant must summarize the result itself.",
                parameters={
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "Optional stable id."},
                        "name": {"type": "string"},
                        "path": {"type": "string", "description": "Local Markdown file or directory."},
                        "uri": {"type": "string", "description": "Alias for path in v1."},
                        "kind": {"type": "string", "enum": ["markdown"]},
                        "scope": {"type": "string", "enum": sorted(_SCOPES)},
                        "audience": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "enabled": {"type": "boolean"},
                    },
                    "required": ["name", "scope"],
                },
            ),
            source_add,
        ),
        "rag_source_list": ToolEntry(
            ToolDefinition(
                name="rag_source_list",
                description="List registered RAG sources.",
                parameters={"type": "object", "properties": {"include_disabled": {"type": "boolean"}}, "required": []},
            ),
            source_list,
        ),
        "rag_source_sync": ToolEntry(
            ToolDefinition(
                name="rag_source_sync",
                description="Catalogue one or all enabled Markdown RAG sources and deeply index only tagged chunks.",
                parameters={"type": "object", "properties": {"source_id": {"type": "string"}}, "required": []},
            ),
            source_sync,
        ),
        "rag_search": ToolEntry(
            ToolDefinition(
                name="rag_search",
                description="Search indexed Markdown RAG sources. Empty query returns important non-archived chunks.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "source_id": {"type": "string"},
                        "scope": {"type": "string"},
                        "tag": {"type": "string"},
                        "include_archived": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                    "required": [],
                },
            ),
            search,
        ),
        "rag_get": ToolEntry(
            ToolDefinition(
                name="rag_get",
                description="Read one indexed RAG chunk by id.",
                parameters={"type": "object", "properties": {"chunk_id": {"type": "integer"}}, "required": ["chunk_id"]},
            ),
            get,
        ),
        "rag_promote_to_memory": ToolEntry(
            ToolDefinition(
                name="rag_promote_to_memory",
                description="Promote a RAG chunk or explicit content to durable memory after the assistant decides it is worth keeping.",
                parameters={
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "integer"},
                        "content": {"type": "string"},
                        "memory_scope": {"type": "string", "enum": ["global", "project"]},
                    },
                    "required": [],
                },
            ),
            promote_to_memory,
        ),
        "rag_checklist_add": ToolEntry(
            ToolDefinition(
                name="rag_checklist_add",
                description="Append unchecked Markdown checklist items (`- [ ] ...`) to a source file or local RAG list.",
                parameters={
                    "type": "object",
                    "properties": {
                        "item": {"type": "string", "description": "Single checklist item to add."},
                        "items": {"type": "array", "items": {"type": "string"}},
                        "path": {"type": "string", "description": "Explicit Markdown file path. Use when known."},
                        "source_id": {"type": "string", "description": "Optional source id to resync after writing."},
                        "list_name": {"type": "string", "description": "Fallback local list name when no path is known."},
                    },
                    "required": [],
                },
            ),
            checklist_add,
        ),
    }


def _search_result(chunks: list[RagChunk], documents: list[Any], title: str) -> ToolResult:
    if not chunks and not documents:
        return ToolResult(tool_call_id="", ok=True, summary=f"{title}: no result.", data={"chunks": [], "documents": []})
    lines = [f"{title}: {len(chunks)} indexed chunk(s), {len(documents)} document match(es)."]
    for chunk in chunks:
        tags = f" [{chunk.tags}]" if chunk.tags else ""
        lines.append(f"- #{chunk.id} {chunk.source_name}/{chunk.title}{tags}: {_preview(chunk.content)}")
    for document in documents:
        tags = f" [{document.tags}]" if document.tags else ""
        details: list[str] = []
        if document.checklist_open or document.checklist_done:
            details.append(f"{document.checklist_open} open / {document.checklist_done} done checklist")
        if document.bullet_count:
            details.append(f"{document.bullet_count} bullet(s)")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- document {document.source_name}/{document.title}{tags}: {document.path}{suffix}")
    chunk_markdown = "\n\n".join(
        f"## #{chunk.id} {chunk.source_name} — {chunk.title}\n\n"
        f"Path: `{chunk.path}` line {chunk.line_start}\n\n{chunk.content}"
        for chunk in chunks
    )
    document_markdown = "\n\n".join(
        f"## Document {document.source_name} — {document.title}\n\n"
        f"Path: `{document.path}`\n\n"
        f"Inventory: {document.checklist_open} open checklist, "
        f"{document.checklist_done} done checklist, {document.bullet_count} bullet(s)."
        for document in documents
    )
    markdown = "\n\n".join(part for part in (chunk_markdown, document_markdown) if part)
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary="\n".join(lines),
        data={
            "chunks": [chunk_to_dict(chunk) for chunk in chunks],
            "documents": [document_hit_to_dict(document) for document in documents],
        },
        artifacts=[Artifact(type=ArtifactType.REPORT, path="rag-results.md", data={"content": markdown})],
    )


def _chunks_result(chunks: list[RagChunk], title: str) -> ToolResult:
    return _search_result(chunks, [], title)


def _memory_content(chunk: RagChunk) -> str:
    return f"{chunk.title}: {chunk.content.strip()}"


def _document_summary_line(document: Any, source: RagSource) -> str:
    path = Path(document.path)
    try:
        label = str(path.relative_to(Path(source.uri)))
    except ValueError:
        label = path.name
    details: list[str] = []
    if document.indexed_chunk_count:
        details.append(f"{document.indexed_chunk_count}/{document.chunk_count} chunk(s) indexed")
    elif document.chunk_count:
        details.append(f"{document.chunk_count} chunk(s) catalogued")
    if document.checklist_open or document.checklist_done:
        details.append(f"{document.checklist_open} open / {document.checklist_done} done checklist")
    if document.bullet_count:
        details.append(f"{document.bullet_count} bullet(s)")
    if document.tags:
        details.append(f"tags {document.tags}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{label}: {document.title}{suffix}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_checklist_path(path_text: str, *, list_name: str, source: RagSource | None, base: Path) -> Path:
    if path_text:
        return Path(path_text).expanduser()
    filename = _slug(list_name) + ".md"
    if source is not None:
        root = Path(source.uri).expanduser()
        if root.is_file():
            return root
        return root / "lists" / filename
    return base / "lists" / filename


def _title_from_path(path: Path, list_name: str) -> str:
    stem = path.stem or list_name
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _is_checklist_line(line: str) -> bool:
    return line.strip().startswith("- [ ]") or line.strip().startswith("- [x]") or line.strip().startswith("- [X]")


def _normalize_item(line: str) -> str:
    stripped = line.strip()
    for prefix in ("- [ ]", "- [x]", "- [X]"):
        if stripped.startswith(prefix):
            return _normalize_text(stripped[len(prefix):])
    return _normalize_text(stripped)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-") or "todo"


def _string_list(value: Any, *, preserve_case: bool = False) -> list[str]:
    if not isinstance(value, list):
        return []
    strings = [str(item).strip() for item in value if str(item).strip()]
    if preserve_case:
        return strings
    return [item.lower() for item in strings]


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int):
        return default
    return max(minimum, min(maximum, value))


def _preview(text: str, limit: int = 180) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "..."
