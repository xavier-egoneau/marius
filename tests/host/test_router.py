from __future__ import annotations

from marius.host.router import HostRouter, InboundRequest
from marius.kernel.contracts import ContextUsage
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig
from marius.kernel.runtime import RuntimeOrchestrator
from marius.storage.ui_history import InMemoryVisibleHistoryStore


def test_host_router_routes_request_through_runtime_and_records_visible_history() -> None:
    orchestrator = RuntimeOrchestrator(
        provider=InMemoryProviderAdapter(
            config=ProviderConfig(provider_name="test", model="stub-model"),
            completion_text="Réponse finale",
            usage=ContextUsage(provider_input_tokens=12, max_context_tokens=1000),
        )
    )
    history_store = InMemoryVisibleHistoryStore()
    router = HostRouter(
        orchestrator=orchestrator,
        history_store=history_store,
        system_prompt="Tu es Marius.",
    )

    payload = router.route(
        InboundRequest(
            channel="telegram",
            session_id="canon",
            peer_id="user-1",
            text="Salut Marius",
            metadata={"topic": "demo"},
        )
    )

    assert payload.text == "Réponse finale"
    assert payload.metadata["status"] == "completed"
    assert payload.metadata["session_id"] == "canon"
    assert payload.metadata["channel"] == "telegram"
    assert payload.metadata["peer_id"] == "user-1"
    assert len(history_store.list_entries("canon")) == 2
    assert history_store.list_entries("canon")[0].role == "user"
    assert history_store.list_entries("canon")[1].role == "assistant"
    assert router.sessions["canon"].state.turns[0].metadata["status"] == "completed"
    assert orchestrator.provider is not None
    assert orchestrator.provider.calls[0].metadata["topic"] == "demo"


def test_host_router_returns_fallback_text_when_no_provider_is_configured() -> None:
    router = HostRouter(orchestrator=RuntimeOrchestrator())

    payload = router.route(
        InboundRequest(
            channel="cli",
            session_id="local-1",
            peer_id="local",
            text="Teste le host",
        )
    )

    assert payload.text == "Requête prête pour le provider."
    assert payload.metadata["status"] == "ready_for_provider"
    assert payload.metadata["session_id"] == "local-1"
