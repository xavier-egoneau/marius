from __future__ import annotations

from datetime import datetime

from marius.host.router import HostRouter, InboundRequest
from marius.kernel.contracts import Artifact, ArtifactType, ContextUsage, Message, Role, ToolResult
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig
from marius.kernel.runtime import RuntimeOrchestrator, TurnOutput
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


class _ArtifactOrchestrator:
    def run_turn(self, *_args, **_kwargs) -> TurnOutput:
        return TurnOutput(
            assistant_message=Message(
                role=Role.ASSISTANT,
                content="Patch prêt.",
                created_at=datetime(2026, 5, 8, 9, 0, 0),
            ),
            tool_results=[
                ToolResult(
                    tool_call_id="tool-1",
                    ok=True,
                    artifacts=[
                        Artifact(
                            type=ArtifactType.DIFF,
                            path="README.md",
                            data={"patch": "@@ -1 +1 @@\n-old\n+new"},
                        )
                    ],
                )
            ],
            metadata={"status": "completed"},
        )


def test_host_router_keeps_tool_artifacts_visible_in_payload_and_history() -> None:
    history_store = InMemoryVisibleHistoryStore()
    router = HostRouter(
        orchestrator=_ArtifactOrchestrator(),  # type: ignore[arg-type]
        history_store=history_store,
    )

    payload = router.route(
        InboundRequest(
            channel="telegram",
            session_id="canon",
            peer_id="user-1",
            text="Montre le patch",
        )
    )

    assert "Patch prêt." in payload.text
    assert "**Diff — `README.md`**" in payload.text
    assert "+new" in payload.text
    assert history_store.list_entries("canon")[1].content == payload.text
