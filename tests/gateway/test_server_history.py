from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from marius.gateway.server import GatewayServer
from marius.gateway.server import _hydrate_session_from_visible_history
from marius.kernel.contracts import Message, Role
from marius.kernel.session import SessionRuntime


def test_hydrates_recent_visible_pairs_into_session() -> None:
    session = SessionRuntime(session_id="main")

    restored = _hydrate_session_from_visible_history(
        session,
        [
            {"role": "user", "content": "/plan build it"},
            {"role": "assistant", "content": "Plan written."},
            {"role": "user", "content": "/dev"},
            {"role": "assistant", "content": "Implemented and committed."},
        ],
    )

    messages = session.internal_messages()
    assert restored == 2
    assert [message.content for message in messages] == [
        "/plan build it",
        "Plan written.",
        "/dev",
        "Implemented and committed.",
    ]
    assert all(turn.metadata["status"] == "restored" for turn in session.state.turns)


def test_hydration_is_best_effort_and_does_not_duplicate_existing_session() -> None:
    session = SessionRuntime(session_id="main")
    _hydrate_session_from_visible_history(
        session,
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )

    restored = _hydrate_session_from_visible_history(
        session,
        [
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "response"},
        ],
    )

    assert restored == 0
    assert len(session.state.turns) == 1


def test_hydration_skips_unpaired_messages_and_caps_turns() -> None:
    session = SessionRuntime(session_id="main")

    restored = _hydrate_session_from_visible_history(
        session,
        [
            {"role": "assistant", "content": "orphan"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "one"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "unanswered"},
        ],
        max_turns=1,
    )

    messages = session.internal_messages()
    assert restored == 1
    assert [message.content for message in messages] == ["second", "two"]


def test_hydration_respects_latest_compaction_boundary() -> None:
    session = SessionRuntime(session_id="main")

    restored = _hydrate_session_from_visible_history(
        session,
        [
            {"role": "user", "content": "ancienne question"},
            {"role": "assistant", "content": "ancienne réponse"},
            {"role": "system", "content": "", "metadata": {"kind": "compaction_boundary"}},
            {"role": "user", "content": "question fraîche"},
            {"role": "assistant", "content": "réponse fraîche"},
        ],
    )

    messages = session.internal_messages()
    assert restored == 1
    assert [message.content for message in messages] == ["question fraîche", "réponse fraîche"]


def test_new_conversation_resets_runtime_session_metadata(monkeypatch) -> None:
    gateway = GatewayServer.__new__(GatewayServer)
    gateway.agent_name = "main"
    gateway.entry = SimpleNamespace(name="provider-1", model="model-1")
    gateway._turn_lock = __import__("threading").Lock()
    gateway.session = SessionRuntime(
        session_id="main",
        metadata={
            "provider": "provider-1",
            "model": "model-1",
            "session_observations": ["old observation"],
            "posture": "dev",
        },
    )
    turn = gateway.session.start_turn(
        user_message=Message(
            role=Role.USER,
            content="ancienne question",
            created_at=datetime.now(timezone.utc),
        )
    )
    gateway.session.finish_turn(
        turn.id,
        assistant_message=Message(
            role=Role.ASSISTANT,
            content="ancienne réponse",
            created_at=datetime.now(timezone.utc),
        ),
    )
    archived: list[str] = []
    monkeypatch.setattr("marius.gateway.server._archive_and_clear_visible_history", lambda agent: archived.append(agent))
    monkeypatch.setattr("marius.gateway.server.log_event", lambda *_args, **_kwargs: None)

    gateway.new_conversation(clear_visible=True, channel="web", reason="test")

    assert gateway.session.state.turns == []
    assert gateway.session.state.compaction_notices == []
    assert gateway.session.state.derived_context_summary == ""
    assert gateway.session.state.derived_context_summary_message is None
    assert gateway.session.state.metadata == {"provider": "provider-1", "model": "model-1"}
    assert archived == ["main"]
