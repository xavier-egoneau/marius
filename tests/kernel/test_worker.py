"""Tests du worker délégué."""

from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.worker import (
    MAX_FILE_CONTEXT_CHARS,
    WorkerResult,
    WorkerTask,
    _build_system_prompt,
    _load_relevant_files,
    _parse_report,
)


# ── _build_system_prompt ──────────────────────────────────────────────────────


def _task(**kwargs) -> WorkerTask:
    defaults = dict(task="Écrire les tests", context_summary="", relevant_files=[], write_paths=[])
    return WorkerTask(**{**defaults, **kwargs})


def test_prompt_contains_mission() -> None:
    p = _build_system_prompt(_task(task="Implémenter le parser"), "")
    assert "Implémenter le parser" in p


def test_prompt_contains_constraints() -> None:
    p = _build_system_prompt(_task(), "")
    assert "Ne spawne pas" in p
    assert "needs_arbitration" in p
    assert "orchestrateur" in p


def test_prompt_contains_report_format() -> None:
    p = _build_system_prompt(_task(), "")
    assert "status:" in p
    assert "changed_files:" in p
    assert "blocker:" in p


def test_prompt_includes_context_summary() -> None:
    p = _build_system_prompt(_task(context_summary="Le module X gère Y."), "")
    assert "Le module X gère Y." in p


def test_prompt_includes_write_paths() -> None:
    p = _build_system_prompt(_task(write_paths=["src/out.py", "tests/test_out.py"]), "")
    assert "src/out.py" in p


def test_prompt_includes_file_context() -> None:
    p = _build_system_prompt(_task(), "### foo.py\n```\ndef foo(): pass\n```")
    assert "foo.py" in p
    assert "def foo()" in p


def test_prompt_no_spawn_agent_reference_in_report() -> None:
    p = _build_system_prompt(_task(), "")
    # Le rapport ne doit pas suggérer de spawner depuis le worker
    assert "spawn_agent" not in p


# ── _parse_report ─────────────────────────────────────────────────────────────


def _make_response(*lines: str) -> str:
    return "\n".join(lines)


def test_parse_completed() -> None:
    r = _parse_report(_make_response(
        "J'ai fait le travail.",
        "status: completed",
        "summary: Tests écrits et passants",
        "changed_files: tests/test_foo.py",
        "verification: pytest — 5 passed",
        "blocker: none",
    ))
    assert r["status"] == "completed"
    assert "Tests écrits" in r["summary"]
    assert r["blocker"] == "none"


def test_parse_blocked() -> None:
    r = _parse_report(_make_response(
        "status: blocked",
        "summary: Fichier manquant",
        "changed_files: none",
        "verification: not_run: bloqué",
        "blocker: Le fichier config.py est introuvable",
    ))
    assert r["status"] == "blocked"
    assert "config.py" in r["blocker"]


def test_parse_needs_arbitration() -> None:
    r = _parse_report(_make_response(
        "status: needs_arbitration",
        "summary: Besoin de paralléliser 3 sous-tâches",
        "changed_files: none",
        "verification: not_run: en attente",
        "blocker: Besoin de workers pour parser A, B, C",
    ))
    assert r["status"] == "needs_arbitration"
    assert "workers" in r["blocker"].lower()


def test_parse_report_in_code_block() -> None:
    r = _parse_report(
        "Travail effectué.\n\n```\n"
        "status: completed\n"
        "summary: Fait\n"
        "changed_files: none\n"
        "verification: ok\n"
        "blocker: none\n"
        "```"
    )
    assert r["status"] == "completed"


def test_parse_empty_response() -> None:
    r = _parse_report("")
    assert r == {}


def test_parse_report_at_end_wins() -> None:
    # Si le worker mentionne 'status: blocked' dans le texte, c'est le dernier
    # qui compte (le rapport est à la fin)
    r = _parse_report(
        "Je vois que status: blocked pourrait s'appliquer.\n"
        "Mais finalement :\n"
        "status: completed\n"
        "summary: Tout va bien\n"
        "changed_files: none\n"
        "verification: ok\n"
        "blocker: none\n"
    )
    assert r["status"] == "completed"


# ── _load_relevant_files ──────────────────────────────────────────────────────


def test_load_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    f.write_text("def foo(): pass")
    result = _load_relevant_files(["foo.py"], tmp_path)
    assert "foo.py" in result
    assert "def foo()" in result


def test_load_missing_file(tmp_path: Path) -> None:
    result = _load_relevant_files(["missing.py"], tmp_path)
    assert "introuvable" in result


def test_load_truncates_at_limit(tmp_path: Path) -> None:
    f = tmp_path / "big.py"
    f.write_text("x" * (MAX_FILE_CONTEXT_CHARS + 1000))
    result = _load_relevant_files(["big.py"], tmp_path)
    assert "tronqué" in result
    assert len(result) < MAX_FILE_CONTEXT_CHARS + 500


def test_load_multiple_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "b.py").write_text("# b")
    result = _load_relevant_files(["a.py", "b.py"], tmp_path)
    assert "a.py" in result
    assert "b.py" in result


def test_load_empty_list(tmp_path: Path) -> None:
    assert _load_relevant_files([], tmp_path) == ""


# ── WorkerResult ──────────────────────────────────────────────────────────────


def test_worker_result_fields() -> None:
    r = WorkerResult(
        task="Écrire des tests",
        status="completed",
        summary="5 tests écrits",
        changed_files=["tests/test_foo.py"],
        blocker="none",
        verification="pytest — 5 passed",
        elapsed_seconds=12.3,
    )
    assert r.status == "completed"
    assert r.elapsed_seconds == pytest.approx(12.3)
    assert "tests/test_foo.py" in r.changed_files
