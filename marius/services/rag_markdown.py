"""Markdown parsing helpers for RAG sources.

Pure stdlib module: it turns Markdown files into tagged chunks without knowing
about Marius runtime, tools, or storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KNOWN_TAGS = {"always", "important", "routine", "fresh", "archive"}

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_INLINE_TAG_RE = re.compile(r"\[([A-Za-z0-9_-]+)\]")
_OBSIDIAN_TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")


@dataclass(frozen=True)
class MarkdownChunk:
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    importance: int = 10
    archived: bool = False
    line_start: int = 1


@dataclass(frozen=True)
class MarkdownDocument:
    path: Path
    title: str
    metadata: dict[str, Any]
    tags: list[str]
    chunks: list[MarkdownChunk]


def parse_markdown_file(path: Path) -> MarkdownDocument:
    source_path = Path(path)
    raw = source_path.read_text(encoding="utf-8")
    metadata, body, body_start = _split_frontmatter(raw)
    doc_tags = _string_list(metadata.get("tags"))
    title = _document_title(body, source_path)
    chunks = _chunks_from_body(body, doc_tags=doc_tags, body_start=body_start)
    return MarkdownDocument(
        path=source_path,
        title=title,
        metadata=metadata,
        tags=doc_tags,
        chunks=chunks,
    )


def markdown_files(root: Path) -> list[Path]:
    path = Path(root).expanduser()
    if path.is_file():
        return [path] if path.suffix.lower() in (".md", ".markdown") else []
    if not path.is_dir():
        return []
    return sorted(
        file
        for file in path.rglob("*")
        if file.is_file()
        and file.suffix.lower() in (".md", ".markdown")
        and not any(part.startswith(".") for part in file.relative_to(path).parts)
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str, int]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw, 1
    metadata = _parse_frontmatter(match.group(1))
    body = raw[match.end():]
    body_start = raw[:match.end()].count("\n") + 1
    return metadata, body, body_start


def _parse_frontmatter(raw: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            metadata[key] = [
                item.strip().strip("\"'")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
        else:
            metadata[key] = value.strip("\"'")
    return metadata


def _document_title(body: str, path: Path) -> str:
    for line in body.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            return _strip_inline_tags(match.group(2)).strip()
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def _chunks_from_body(body: str, *, doc_tags: list[str], body_start: int) -> list[MarkdownChunk]:
    chunks: list[MarkdownChunk] = []
    current_title = ""
    current_lines: list[str] = []
    current_start = body_start

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if not content:
            return
        tags = _merge_tags(doc_tags, _tags_in_text(content), _tags_in_text(current_title))
        chunks.append(MarkdownChunk(
            title=_strip_inline_tags(current_title).strip() or "Note",
            content=content,
            tags=tags,
            importance=_importance(tags),
            archived="archive" in tags,
            line_start=current_start,
        ))

    for offset, line in enumerate(body.splitlines(), start=body_start):
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            current_title = heading.group(2)
            current_lines = [line]
            current_start = offset
            continue
        if not current_lines and line.strip():
            current_start = offset
        current_lines.append(line)
    flush()
    return chunks


def _tags_in_text(text: str) -> list[str]:
    tags: list[str] = []
    for tag in _INLINE_TAG_RE.findall(text):
        normalized = tag.strip().lower()
        if normalized:
            tags.append(normalized)
    for tag in _OBSIDIAN_TAG_RE.findall(text):
        normalized = tag.strip().lower().replace("/", "-")
        if normalized:
            tags.append(normalized)
    return _merge_tags(tags)


def _merge_tags(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for tag in group:
            normalized = str(tag).strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
    return merged


def _importance(tags: list[str]) -> int:
    tag_set = set(tags)
    if "always" in tag_set:
        return 100
    if "important" in tag_set:
        return 80
    if "fresh" in tag_set:
        return 65
    if "routine" in tag_set:
        return 55
    if "archive" in tag_set:
        return 0
    return 10


def _strip_inline_tags(text: str) -> str:
    cleaned = _INLINE_TAG_RE.sub("", text)
    cleaned = re.sub(r"\s+([,;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:\s*[,;:]\s*)+$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _merge_tags([str(item) for item in value])
    if isinstance(value, str):
        return _merge_tags([
            part.strip()
            for part in value.replace("#", "").split(",")
            if part.strip()
        ])
    return []
