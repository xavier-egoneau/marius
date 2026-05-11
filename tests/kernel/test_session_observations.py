from __future__ import annotations

from pathlib import Path

from marius.kernel.contracts import ToolCall, ToolResult
from marius.kernel.session_observations import format_session_observations, observe_tool_result


def test_observes_prefixed_list_dir_paths(tmp_path: Path) -> None:
    metadata: dict = {}
    call = ToolCall(id="c1", name="list_dir", arguments={"path": "./wysiwyg"})
    result = ToolResult(
        tool_call_id="c1",
        ok=True,
        summary="Dossier : wysiwyg\n📁 wysiwyg/js\n  wysiwyg/checks.html",
        data={"path": "./wysiwyg"},
    )

    observe_tool_result(metadata, call, result, project_root=tmp_path)

    block = format_session_observations(metadata)
    assert "<session_observations>" in block
    assert "`wysiwyg/checks.html`" in block
    assert "`wysiwyg/js`" in block


def test_observes_file_not_found_candidates(tmp_path: Path) -> None:
    metadata: dict = {}
    call = ToolCall(id="c1", name="read_file", arguments={"path": "./checks.html"})
    result = ToolResult(
        tool_call_id="c1",
        ok=False,
        summary=(
            "Fichier introuvable : checks.html. "
            "Candidat(s) existant(s) dans le projet : wysiwyg/checks.html. "
            "Utilise un chemin listé ou liste le dossier parent avant de réessayer."
        ),
        error="file_not_found",
    )

    observe_tool_result(metadata, call, result, project_root=tmp_path)

    block = format_session_observations(metadata)
    assert "Chemin invalide `checks.html`" in block
    assert "`wysiwyg/checks.html`" in block


def test_observes_verified_file_path_and_deduplicates(tmp_path: Path) -> None:
    metadata: dict = {}
    call = ToolCall(id="c1", name="read_file", arguments={"path": "wysiwyg/js/core.js"})
    result = ToolResult(
        tool_call_id="c1",
        ok=True,
        summary="content",
        data={"path": "wysiwyg/js/core.js"},
    )

    observe_tool_result(metadata, call, result, project_root=tmp_path)
    observe_tool_result(metadata, call, result, project_root=tmp_path)

    observations = metadata["session_observations"]
    assert len(observations) == 1
    assert observations[0] == "Chemin fichier vérifié : `wysiwyg/js/core.js`."


def test_formats_empty_observations_as_empty_string() -> None:
    assert format_session_observations({}) == ""
