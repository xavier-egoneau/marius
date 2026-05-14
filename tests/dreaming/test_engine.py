"""Tests du moteur dreaming/daily.

_call_llm est mocké — on teste l'orchestration sans appel réseau réel.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from marius.dreaming.engine import LLMCallResult, run_daily, run_dreaming
from marius.kernel.contracts import ContextUsage
from marius.storage.memory_store import MemoryStore


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def memory_store(tmp_path: Path) -> MemoryStore:
    s = MemoryStore(db_path=tmp_path / "memory.db")
    yield s
    s.close()


@pytest.fixture()
def entry() -> SimpleNamespace:
    return SimpleNamespace(
        name="test-provider",
        provider="openai",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        auth_type="auth",
        metadata={},
    )


def _dream_llm_response(ops: list[dict], summary: str = "Dream OK.") -> str:
    return json.dumps({"operations": ops, "summary": summary})


# ── run_dreaming — contexte vide ──────────────────────────────────────────────


def test_run_dreaming_empty_context_returns_early(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    result = run_dreaming(
        memory_store=memory_store,
        entry=entry,
        project_root=tmp_path,

        archive_sessions=False,
    )
    assert "vide" in result.summary.lower() or "rien" in result.summary.lower()


# ── run_dreaming — chemin normal ──────────────────────────────────────────────


def test_run_dreaming_applies_add_operation(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("fait initial")   # contexte non vide

    llm_reply = _dream_llm_response([
        {"op": "add", "content": "Nouveau fait", "scope": "global", "tags": ""},
    ], summary="1 ajouté.")

    with patch("marius.dreaming.engine._call_llm", return_value=llm_reply):
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
            archive_sessions=False,
        )

    assert result.added == 1
    assert result.errors == 0
    memories = memory_store.list()
    contents = [m.content for m in memories]
    assert any("Nouveau fait" in c for c in contents)


def test_run_dreaming_returns_llm_summary(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("fait X")

    llm_reply = _dream_llm_response([], summary="Résumé LLM spécifique.")

    with patch("marius.dreaming.engine._call_llm", return_value=llm_reply):
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
            archive_sessions=False,
        )

    assert "Résumé LLM spécifique." in result.summary


def test_run_dreaming_saves_dream_report(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("fait Y")
    dreams_dir = tmp_path / "dreams"

    llm_reply = _dream_llm_response([], summary="OK")

    with patch("marius.dreaming.engine._call_llm", return_value=llm_reply):
        run_dreaming(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
            dreams_dir=dreams_dir,
    
            archive_sessions=False,
        )

    reports = list(dreams_dir.glob("dream_*.json")) if dreams_dir.exists() else []
    assert len(reports) == 1


# ── run_dreaming — provider error ─────────────────────────────────────────────


def test_run_dreaming_provider_error_returns_gracefully(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("fait Z")
    from marius.kernel.provider import ProviderError

    with patch("marius.dreaming.engine._call_llm", side_effect=ProviderError("timeout")):
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
            archive_sessions=False,
        )

    assert result.errors >= 0   # pas d'exception levée
    assert "provider" in result.summary.lower() or "erreur" in result.summary.lower()


# ── run_dreaming — LLM répond du JSON invalide ───────────────────────────────


def test_run_dreaming_invalid_llm_response_no_crash(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("fait pour tester JSON invalide")

    with patch("marius.dreaming.engine._call_llm", return_value="pas du JSON"):
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
            archive_sessions=False,
        )

    # Aucune opération appliquée, mais pas de crash
    assert result.added == 0


# ── run_daily — contexte vide ─────────────────────────────────────────────────


def test_run_daily_empty_context_returns_placeholder(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    briefing = run_daily(
        memory_store=memory_store,
        entry=entry,
        project_root=tmp_path,

    )
    assert isinstance(briefing, str)
    assert len(briefing) > 0


# ── run_daily — chemin normal ─────────────────────────────────────────────────


def test_run_daily_returns_llm_output(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("Préférence : réponses courtes")

    with patch(
        "marius.dreaming.engine._call_llm_with_usage",
        return_value=LLMCallResult(
            text="# Briefing\n\nTout va bien.",
            usage=ContextUsage(provider_input_tokens=120, provider_output_tokens=20),
            model="gpt-4o",
        ),
    ):
        briefing = run_daily(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
        )

    assert "Briefing" in briefing
    assert "Tout va bien." in briefing
    assert "Tokens daily" in briefing
    assert "total 140" in briefing
    assert "gpt-4o" in briefing


def test_run_daily_can_use_model_override(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("Préférence : réponses courtes")

    with patch(
        "marius.dreaming.engine._call_llm_with_usage",
        return_value=LLMCallResult(
            text="# Briefing\n\nTout va bien.",
            usage=ContextUsage(),
            model="gpt-mini",
        ),
    ) as call:
        briefing = run_daily(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
            model="gpt-mini",
        )

    assert call.call_args.args[0].model == "gpt-mini"
    assert "modèle `gpt-mini`" in briefing


def test_run_daily_provider_error_returns_error_message(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    memory_store.add("Mémoire test")
    from marius.kernel.provider import ProviderError

    with patch("marius.dreaming.engine._call_llm_with_usage", side_effect=ProviderError("refused")):
        briefing = run_daily(
            memory_store=memory_store,
            entry=entry,
            project_root=tmp_path,
    
        )

    assert "Erreur" in briefing or "erreur" in briefing


# ── GatewayScheduler — dreaming/daily sur tick ───────────────────────────────


def test_scheduler_runner_dream_delegates_to_engine(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    from types import SimpleNamespace
    from marius.gateway.scheduler_runner import GatewayScheduler
    from marius.storage.reminders_store import RemindersStore

    agent_cfg = SimpleNamespace(
        scheduler_enabled=False,   # on appelle manuellement
        dream_time="",
        daily_time="",
    )
    runner = GatewayScheduler(
        agent_name="test",
        workspace=tmp_path,
        memory_store=memory_store,
        entry=entry,
        active_skills=[],
        agent_config=agent_cfg,
        reminders_store=RemindersStore(tmp_path / "reminders.json"),
        get_telegram_chat_id=lambda: None,
    )

    memory_store.add("fait pour dreaming")

    with patch("marius.dreaming.engine._call_llm", return_value=_dream_llm_response([], "ok")):
        runner._run_scheduled_dream()   # ne doit pas lever


def test_scheduler_runner_daily_writes_cache(
    memory_store: MemoryStore, entry, tmp_path: Path
) -> None:
    from types import SimpleNamespace
    from marius.gateway.scheduler_runner import GatewayScheduler
    from marius.storage.reminders_store import RemindersStore

    agent_cfg = SimpleNamespace(
        scheduler_enabled=False,
        dream_time="",
        daily_time="",
    )
    runner = GatewayScheduler(
        agent_name="test",
        workspace=tmp_path,
        memory_store=memory_store,
        entry=entry,
        active_skills=[],
        agent_config=agent_cfg,
        reminders_store=RemindersStore(tmp_path / "reminders.json"),
        get_telegram_chat_id=lambda: None,
    )

    memory_store.add("mémoire pour le daily")

    with (
        patch(
            "marius.dreaming.engine._call_llm_with_usage",
            return_value=LLMCallResult(
                text="# Briefing\n\nBonjour.",
                usage=ContextUsage(provider_input_tokens=10, provider_output_tokens=5),
                model="gpt-4o",
            ),
        ),
        patch("marius.gateway.workspace.daily_cache_path", return_value=tmp_path / "daily.md"),
    ):
        runner._run_scheduled_daily()

    cache = tmp_path / "daily.md"
    assert cache.exists()
    assert "Briefing" in cache.read_text()


