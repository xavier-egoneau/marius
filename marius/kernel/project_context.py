"""Résolution déterministe du contexte projet pour le kernel Marius."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from marius.kernel.context_builder import ContextBuildInput, ContextSource


class RuntimeMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class SessionScope(str, Enum):
    CANONICAL = "canonical"
    PROJECT = "project"
    BRANCH = "branch"


class PermissionMode(str, Enum):
    SAFE = "safe"
    LIMITED = "limited"
    POWER = "power"


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
    permission_mode: PermissionMode = PermissionMode.LIMITED
    workspace_root: Path | None = None
    allowed_roots: list[Path] = field(default_factory=list)
    activate_requested_project: bool = False


@dataclass(slots=True)
class ResolvedProjectContext:
    active_project: ProjectRef | None
    cited_projects: list[ProjectRef]
    preamble: str
    context_input: ContextBuildInput
    permission_mode: PermissionMode
    workspace_root: Path | None = None
    allowed_roots: list[Path] = field(default_factory=list)
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
    def __init__(self, *, catalog: ProjectCatalog, guardian_policy: Any | None = None) -> None:
        self.catalog = catalog
        self.guardian_policy = guardian_policy

    def resolve(self, context_input: ProjectContextInput) -> ResolvedProjectContext:
        self._validate(context_input)

        active_project = context_input.active_project
        allowed_roots = self._normalize_roots(
            context_input.allowed_roots,
            workspace_root=context_input.workspace_root,
        )
        allow_expansion = None
        active_project_promoted = False

        if active_project is not None:
            allowed_roots, allow_expansion, active_project_promoted = self._apply_guardian_policy(
                context_input,
                allowed_roots=allowed_roots,
            )

        preamble = self._build_preamble(
            context_input,
            allowed_roots=allowed_roots,
            allow_expansion=allow_expansion,
            active_project_promoted=active_project_promoted,
        )
        sources: list[ContextSource] = []

        if active_project is not None:
            documents = self.catalog.describe(active_project)
            self._validate_documents_for_project(active_project, documents)
            sources = self._build_sources(documents)

        allow_expansion_status = None
        allow_expansion_code = None
        allow_expansion_roots: list[str] = []
        if allow_expansion is not None:
            allow_expansion_status = allow_expansion.status.value
            allow_expansion_code = allow_expansion.code.value
            allow_expansion_roots = [str(root) for root in allow_expansion.roots_to_add]

        return ResolvedProjectContext(
            active_project=active_project,
            cited_projects=list(context_input.cited_projects),
            preamble=preamble,
            context_input=ContextBuildInput(sources=sources),
            permission_mode=context_input.permission_mode,
            workspace_root=context_input.workspace_root,
            allowed_roots=allowed_roots,
            metadata={
                "mode": context_input.mode.value,
                "session_scope": context_input.session_scope.value,
                "permission_mode": context_input.permission_mode.value,
                "workspace_root": str(context_input.workspace_root)
                if context_input.workspace_root is not None
                else None,
                "allowed_roots": [str(root) for root in allowed_roots],
                "active_project_id": active_project.project_id if active_project else None,
                "cited_project_ids": [project.project_id for project in context_input.cited_projects],
                "branch_id": context_input.branch.branch_id if context_input.branch else None,
                "active_project_promoted": active_project_promoted,
                "allow_expansion_status": allow_expansion_status,
                "allow_expansion_code": allow_expansion_code,
                "allow_expansion_roots": allow_expansion_roots,
            },
        )

    def _validate(self, context_input: ProjectContextInput) -> None:
        if context_input.mode is RuntimeMode.LOCAL and context_input.active_project is None:
            raise ProjectResolutionError("Local mode requires an active project")

        if context_input.session_scope is SessionScope.PROJECT and context_input.active_project is None:
            raise ProjectResolutionError("Project scope requires an active project")

        if context_input.session_scope is SessionScope.BRANCH and context_input.active_project is None:
            raise ProjectResolutionError("Branch scope requires an active project")

        if context_input.session_scope is SessionScope.BRANCH and context_input.branch is None:
            raise ProjectResolutionError("Branch scope requires branch details")

        if context_input.session_scope is not SessionScope.BRANCH and context_input.branch is not None:
            raise ProjectResolutionError("Branch details require branch scope")

        if context_input.branch is not None and context_input.active_project is None:
            raise ProjectResolutionError("A branch cannot exist without an active project")

        if context_input.active_project is not None:
            active_project_id = context_input.active_project.project_id
            cited_project_ids = {project.project_id for project in context_input.cited_projects}
            if active_project_id in cited_project_ids:
                raise ProjectResolutionError(
                    "The active project cannot also be listed as a cited project"
                )

    def _apply_guardian_policy(
        self,
        context_input: ProjectContextInput,
        *,
        allowed_roots: list[Path],
    ) -> tuple[list[Path], Any | None, bool]:
        from marius.kernel.guardian_policy import (
            AllowExpansionCode,
            AllowExpansionDecision,
            AllowExpansionReason,
            AllowExpansionStatus,
            AllowExpansionRequest,
            DefaultGuardianPolicy,
        )

        guardian_policy = self.guardian_policy or DefaultGuardianPolicy()
        active_project = context_input.active_project
        assert active_project is not None
        requested_root = self._normalize_path(active_project.root_path)
        current_allowed_roots = tuple(allowed_roots)
        decision = guardian_policy.review_allow_expansion(
            AllowExpansionRequest(
                permission_mode=context_input.permission_mode,
                workspace_root=self._normalize_path(context_input.workspace_root)
                if context_input.workspace_root is not None
                else None,
                current_allowed_roots=current_allowed_roots,
                requested_root=requested_root,
                reason=AllowExpansionReason.ACTIVATE_PROJECT,
                explicit_user_request=context_input.activate_requested_project,
            )
        )

        if decision.status is AllowExpansionStatus.NOT_REQUIRED:
            return allowed_roots, decision, False

        if decision.status is AllowExpansionStatus.ALLOW:
            updated_roots = list(allowed_roots)
            for root in decision.roots_to_add:
                updated_roots = self._append_unique(updated_roots, self._normalize_path(root))
            active_project_promoted = any(
                self._normalize_path(root) == requested_root for root in decision.roots_to_add
            )
            return updated_roots, decision, active_project_promoted

        message = self._guardian_failure_message(decision.code)
        raise ProjectResolutionError(message)

    def _guardian_failure_message(self, code: Any) -> str:
        if code.value == "explicit_user_request_required":
            return "Limited mode requires an explicit request before allowing an active project outside the current allow zone"
        if code.value == "safe_mode_forbids_expansion":
            return "Safe mode requires the active project to stay inside the allow zone"
        if code.value == "requested_root_too_broad":
            return "The requested root is too broad to be added to the allow zone"
        return "The guardian policy refused the allow expansion request"

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

    def _validate_documents_for_project(
        self,
        project: ProjectRef,
        documents: ProjectDocumentPaths,
    ) -> None:
        project_root = self._normalize_path(project.root_path)
        for path in [documents.agents_path, documents.decisions_path, documents.roadmap_path]:
            if path is None:
                continue
            normalized_path = self._normalize_path(path)
            if normalized_path != project_root and project_root not in normalized_path.parents:
                raise ProjectResolutionError(
                    "Project documents must stay inside the active project's root"
                )

    def _build_preamble(
        self,
        context_input: ProjectContextInput,
        *,
        allowed_roots: list[Path],
        allow_expansion: Any | None,
        active_project_promoted: bool,
    ) -> str:
        lines = [f"Mode {context_input.mode.value}."]
        lines.append(f"Mode permission : {context_input.permission_mode.value}.")

        if context_input.workspace_root is not None:
            lines.append(f"Workspace allow de base : {context_input.workspace_root}.")

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

        if allow_expansion is not None:
            lines.append(
                f"Expansion de zone allow : {allow_expansion.status.value} / {allow_expansion.code.value}."
            )
            if allow_expansion.roots_to_add:
                formatted_roots = ", ".join(str(root) for root in allow_expansion.roots_to_add)
                lines.append(f"Roots à ajouter : {formatted_roots}.")

        if active_project_promoted:
            lines.append(
                "Le projet actif a été ajouté à la zone allow suite à une décision du gardien."
            )

        if allowed_roots:
            formatted_roots = ", ".join(str(root) for root in allowed_roots)
            lines.append(f"Roots allowées effectives : {formatted_roots}.")

        if context_input.branch is not None:
            lines.append(f"Contexte de branche ciblée : {context_input.branch.label}.")
            lines.append(
                "Cette branche décrit un point de vue ciblé sur le projet actif sans fusion implicite avec la session canonique."
            )

        return "\n".join(lines)

    def _normalize_roots(self, roots: list[Path], *, workspace_root: Path | None) -> list[Path]:
        normalized_roots: list[Path] = []
        if workspace_root is not None:
            normalized_roots.append(self._normalize_path(workspace_root))

        for root in roots:
            normalized_roots = self._append_unique(normalized_roots, self._normalize_path(root))
        return normalized_roots

    def _append_unique(self, roots: list[Path], root: Path) -> list[Path]:
        if root in roots:
            return list(roots)
        return [*roots, root]

    def _normalize_path(self, path: Path) -> Path:
        return path.expanduser().resolve(strict=False)
