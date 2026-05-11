from __future__ import annotations

from datetime import datetime

from marius.kernel.compaction import (
    CompactionConfig,
    CompactionLevel,
    compaction_level,
    resolve_token_count,
    total_message_characters,
)
from marius.kernel.contracts import ContextUsage, Message, Role


def test_resolve_token_count_prefers_provider_usage_over_estimate() -> None:
    usage = ContextUsage(
        estimated_input_tokens=1200,
        provider_input_tokens=800,
        max_context_tokens=250000,
    )

    assert resolve_token_count(usage) == 800


def test_resolve_token_count_falls_back_to_estimate_when_provider_usage_missing() -> None:
    usage = ContextUsage(estimated_input_tokens=1200, provider_input_tokens=None)

    assert resolve_token_count(usage) == 1200


def test_total_message_characters_counts_only_message_content() -> None:
    messages = [
        Message(role=Role.USER, content="abc", created_at=datetime(2026, 5, 7, 14, 0, 0)),
        Message(role=Role.ASSISTANT, content="de", created_at=datetime(2026, 5, 7, 14, 0, 1)),
    ]

    assert total_message_characters(messages) == 5


def test_compaction_level_respects_thresholds_from_decisions() -> None:
    config = CompactionConfig(context_window_tokens=100)

    assert compaction_level(59, config) is CompactionLevel.NONE
    assert compaction_level(60, config) is CompactionLevel.TRIM
    assert compaction_level(75, config) is CompactionLevel.SUMMARIZE
    assert compaction_level(90, config) is CompactionLevel.RESET
