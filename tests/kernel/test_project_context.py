from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.context_builder import ContextBuildInput
from marius.kernel.project_context import (
    BranchRef,
    ProjectContextInput,
    ProjectContextResolver,
    ProjectDocumentPaths,
    ProjectRef,
    ProjectResolutionError,
    RuntimeMode,
    SessionScope,
)


class FakeCatalog:
    def __init__(self, documents: dict[str, ProjectDocumentPaths]) -> None:
        self.documents = documents

    def describe(self, project: ProjectRef) -> ProjectDocumentPaths:
        return self.documents[project.project_id]


MARIUS = ProjectRef(
    project_id="marius",
    display_name="Marius",
    root_path=Path("/home/egza/Documents/projets/marius"),
)
MAURICE = ProjectRef(
    project_id="maurice",
    display_name="Maurice",
    root_path=Path("/home/egza/Documents/projets/Maurice"),
)


CATALOG = FakeCatalog(
    {
        "marius": ProjectDocumentPaths(
            agents_path=Path("/home/egza/Documents/projets/marius/AGENTS.md"),
            decisions_path=Path("/home/egza/Documents/projets/marius/DECISIONS.md"),
            roadmap_path=Path("/home/egza/Documents/projets/marius/ROADMAP.md"),
        ),
        "maurice": ProjectDocumentPaths(
            agents_path=Path("/home/egza/Documents/projets/Maurice/AGENTS.md"),
            decisions_path=Path("/home/egza/Documents/projets/Maurice/DECISIONS.md"),
            roadmap_path=Path("/home/egza/Documents/projets/Maurice/ROADMAP.md"),
        ),
    }
)


def test_project_context_requires_active_project_in_local_mode() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    with pytest.raises(ProjectResolutionError):
        resolver.resolve(
            ProjectContextInput(
                mode=RuntimeMode.LOCAL,
                session_scope=SessionScope.PROJECT,
            )
        )


def test_project_context_requires_active_project_for_branch_scope() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    with pytest.raises(ProjectResolutionError):
        resolver.resolve(
            ProjectContextInput(
                mode=RuntimeMode.GLOBAL,
                session_scope=SessionScope.BRANCH,
                branch=BranchRef(branch_id="branch-1", label="Fix auth"),
            )
        )


def test_project_context_requires_branch_details_for_branch_scope() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    with pytest.raises(ProjectResolutionError):
        resolver.resolve(
            ProjectContextInput(
                mode=RuntimeMode.GLOBAL,
                session_scope=SessionScope.BRANCH,
                active_project=MARIUS,
            )
        )


def test_project_context_rejects_active_project_duplicated_in_cited_projects() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    with pytest.raises(ProjectResolutionError):
        resolver.resolve(
            ProjectContextInput(
                mode=RuntimeMode.GLOBAL,
                session_scope=SessionScope.CANONICAL,
                active_project=MARIUS,
                cited_projects=[MARIUS],
            )
        )


def test_project_context_allows_global_scope_without_active_project() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    resolved = resolver.resolve(
        ProjectContextInput(
            mode=RuntimeMode.GLOBAL,
            session_scope=SessionScope.CANONICAL,
            cited_projects=[MARIUS],
        )
    )

    assert resolved.active_project is None
    assert resolved.context_input == ContextBuildInput(sources=[])
    assert resolved.to_context_build_input() == ContextBuildInput(
        sources=[],
        preamble=resolved.preamble,
    )
    assert "Aucun projet actif" in resolved.preamble
    assert resolved.metadata["active_project_id"] is None
    assert resolved.metadata["cited_project_ids"] == ["marius"]


def test_project_context_builds_context_input_for_active_project_only() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    resolved = resolver.resolve(
        ProjectContextInput(
            mode=RuntimeMode.GLOBAL,
            session_scope=SessionScope.CANONICAL,
            active_project=MARIUS,
            cited_projects=[MAURICE],
        )
    )

    assert [source.key for source in resolved.context_input.sources] == [
        "agents",
        "decisions",
        "roadmap",
    ]
    assert [source.path for source in resolved.context_input.sources] == [
        Path("/home/egza/Documents/projets/marius/AGENTS.md"),
        Path("/home/egza/Documents/projets/marius/DECISIONS.md"),
        Path("/home/egza/Documents/projets/marius/ROADMAP.md"),
    ]
    assert all("Maurice" not in str(source.path) for source in resolved.context_input.sources)
    assert resolved.metadata["active_project_id"] == "marius"
    assert resolved.metadata["cited_project_ids"] == ["maurice"]


def test_project_context_preamble_mentions_mode_active_project_and_cited_projects() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    resolved = resolver.resolve(
        ProjectContextInput(
            mode=RuntimeMode.GLOBAL,
            session_scope=SessionScope.CANONICAL,
            active_project=MARIUS,
            cited_projects=[MAURICE],
        )
    )

    assert "Mode global." in resolved.preamble
    assert "Projet actif : Marius" in resolved.preamble
    assert "Projet cité : Maurice" in resolved.preamble
    assert "basculement explicite" in resolved.preamble


def test_project_context_preamble_mentions_branch_context_when_present() -> None:
    resolver = ProjectContextResolver(catalog=CATALOG)

    resolved = resolver.resolve(
        ProjectContextInput(
            mode=RuntimeMode.GLOBAL,
            session_scope=SessionScope.BRANCH,
            active_project=MARIUS,
            branch=BranchRef(branch_id="branch-auth-fix", label="Fix auth"),
        )
    )

    assert "Contexte de branche ciblée : Fix auth" in resolved.preamble
    assert resolved.metadata["branch_id"] == "branch-auth-fix"
    assert resolved.metadata["session_scope"] == SessionScope.BRANCH.value
