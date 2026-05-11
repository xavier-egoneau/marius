from __future__ import annotations

from marius.gateway.server import _hydrate_session_from_visible_history
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
