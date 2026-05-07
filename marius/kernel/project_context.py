"""Résolution déterministe du contexte projet pour le kernel Marius."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from marius.kernel.context_builder import ContextBuildInput, ContextSource


class RuntimeMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class SessionScope(str, Enum):
    CANONICAL = "canonical"
    PROJECT = "project"
    BRANCH = "branch"


@dataclass(slots=True, frozen=True)
class ProjectRef:
    project_id: str
    display_name: str
    root_path: Path


@dataclass(slots=True, frozen=True)
class BranchRef:
    branch_id: str
    label: str


@dataclass(slots=True, frozen=True)
class ProjectDocumentPaths:
    agents_path: Path | None = None
    decisions_path: Path | None = None
    roadmap_path: Path | None = None


@dataclass(slots=True)
class ProjectContextInput:
    mode: RuntimeMode
    session_scope: SessionScope
    active_project: ProjectRef | None = None
    cited_projects: list[ProjectRef] = field(default_factory=list)
    branch: BranchRef | None = None


@dataclass(slots=True)
class ResolvedProjectContext:
    active_project: ProjectRef | None
    cited_projects: list[ProjectRef]
    preamble: str
    context_input: ContextBuildInput
    metadata: dict[str, object] = field(default_factory=dict)

    def to_context_build_input(self) -> ContextBuildInput:
        return ContextBuildInput(
            sources=list(self.context_input.sources),
            preamble=self.preamble,
        )


class ProjectCatalog(Protocol):
    def describe(self, project: ProjectRef) -> ProjectDocumentPaths:
        ...


class ProjectResolutionError(ValueError):
    pass


class ProjectContextResolver:
    def __init__(self, *, catalog: ProjectCatalog) -> None:
        self.catalog = catalog

    def resolve(self, context_input: ProjectContextInput) -> ResolvedProjectContext:
        self._validate(context_input)

        active_project = context_input.active_project
        preamble = self._build_preamble(context_input)
        sources: list[ContextSource] = []

        if active_project is not None:
            documents = self.catalog.describe(active_project)
            sources = self._build_sources(documents)

        return ResolvedProjectContext(
            active_project=active_project,
            cited_projects=list(context_input.cited_projects),
            preamble=preamble,
            context_input=ContextBuildInput(sources=sources),
            metadata={
                "mode": context_input.mode.value,
                "session_scope": context_input.session_scope.value,
                "active_project_id": active_project.project_id if active_project else None,
                "cited_project_ids": [project.project_id for project in context_input.cited_projects],
                "branch_id": context_input.branch.branch_id if context_input.branch else None,
            },
        )

    def _validate(self, context_input: ProjectContextInput) -> None:
        if context_input.mode is RuntimeMode.LOCAL and context_input.active_project is None:
            raise ProjectResolutionError("Local mode requires an active project")

        if context_input.session_scope is SessionScope.BRANCH and context_input.active_project is None:
            raise ProjectResolutionError("Branch scope requires an active project")

        if context_input.session_scope is SessionScope.BRANCH and context_input.branch is None:
            raise ProjectResolutionError("Branch scope requires branch details")

        if context_input.branch is not None and context_input.active_project is None:
            raise ProjectResolutionError("A branch cannot exist without an active project")

        if context_input.active_project is not None:
            active_project_id = context_input.active_project.project_id
            cited_project_ids = {project.project_id for project in context_input.cited_projects}
            if active_project_id in cited_project_ids:
                raise ProjectResolutionError(
                    "The active project cannot also be listed as a cited project"
                )

    def _build_sources(self, documents: ProjectDocumentPaths) -> list[ContextSource]:
        ordered_documents = [
            ("agents", "AGENTS", documents.agents_path),
            ("decisions", "DECISIONS", documents.decisions_path),
            ("roadmap", "ROADMAP", documents.roadmap_path),
        ]

        sources: list[ContextSource] = []
        for key, title, path in ordered_documents:
            if path is None:
                continue
            sources.append(ContextSource(key=key, title=title, path=path))
        return sources

    def _build_preamble(self, context_input: ProjectContextInput) -> str:
        lines = [f"Mode {context_input.mode.value}."]
        active_project = context_input.active_project

        if active_project is None:
            lines.append("Aucun projet actif n'est actuellement fixé.")
        else:
            lines.append(
                f"Projet actif : {active_project.display_name} ({active_project.root_path})."
            )

        for project in context_input.cited_projects:
            lines.append(f"Projet cité : {project.display_name}.")

        if context_input.cited_projects:
            lines.append(
                "Les projets cités restent des références tant qu'un basculement explicite n'a pas eu lieu."
            )

        if context_input.branch is not None:
            lines.append(f"Contexte de branche ciblée : {context_input.branch.label}.")
            lines.append(
                "Cette branche décrit un point de vue ciblé sur le projet actif sans fusion implicite avec la session canonique."
            )

        return "\n".join(lines)
