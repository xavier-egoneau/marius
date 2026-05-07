"""Assemblage déterministe du contexte Markdown pour le kernel Marius."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class MarkdownSourceReader(Protocol):
    def read_text(self, path: Path) -> str | None:
        ...


@dataclass(slots=True)
class ContextSource:
    key: str
    title: str
    path: Path
    required: bool = True


@dataclass(slots=True)
class ContextBuildInput:
    sources: list[ContextSource]
    preamble: str = ""


@dataclass(slots=True)
class ContextBundle:
    markdown: str
    loaded_sources: list[ContextSource] = field(default_factory=list)
    missing_optional_sources: list[ContextSource] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class MissingContextSourceError(FileNotFoundError):
    def __init__(self, source: ContextSource) -> None:
        super().__init__(f"Missing required context source: {source.path}")
        self.source = source


class ContextBuilder:
    def __init__(self, *, reader: MarkdownSourceReader) -> None:
        self.reader = reader

    def build(self, build_input: ContextBuildInput) -> ContextBundle:
        sections: list[str] = []
        loaded_sources: list[ContextSource] = []
        missing_optional_sources: list[ContextSource] = []

        preamble = build_input.preamble.strip()
        if preamble:
            sections.append(preamble)

        for source in build_input.sources:
            raw_content = self.reader.read_text(source.path)
            if raw_content is None:
                if source.required:
                    raise MissingContextSourceError(source)
                missing_optional_sources.append(source)
                continue

            content = raw_content.strip()
            if not content:
                if source.required:
                    raise MissingContextSourceError(source)
                continue

            loaded_sources.append(source)
            sections.append(f"## {source.title}\n{content}")

        return ContextBundle(
            markdown="\n\n".join(sections),
            loaded_sources=loaded_sources,
            missing_optional_sources=missing_optional_sources,
            metadata={
                "source_count": len(loaded_sources),
                "loaded_source_keys": [source.key for source in loaded_sources],
                "has_preamble": bool(preamble),
            },
        )
