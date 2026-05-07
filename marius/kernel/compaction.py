"""Compaction du contexte interne.

Le moteur de compaction réduit la pression de contexte sans détruire
l'historique visible utilisateur, qui relève d'une autre couche.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .contracts import ContextUsage, Message


class CompactionLevel(str, Enum):
    NONE = "none"
    TRIM = "trim"
    SUMMARIZE = "summarize"
    RESET = "reset"


@dataclass(slots=True)
class CompactionConfig:
    context_window_tokens: int = 250_000
    trim_threshold: float = 0.60
    summarize_threshold: float = 0.75
    reset_threshold: float = 0.90
    keep_recent_turns: int = 10


def total_message_characters(messages: Sequence[Message]) -> int:
    return sum(len(message.content) for message in messages)


def estimate_tokens_from_chars(char_count: int, *, chars_per_token: int = 4) -> int:
    """Approximation simple tant qu'aucun tokenizer dédié n'est branché."""
    if char_count <= 0:
        return 0
    return max(1, char_count // max(chars_per_token, 1))


def estimate_tokens_from_messages(
    messages: Sequence[Message],
    *,
    chars_per_token: int = 4,
) -> int:
    return estimate_tokens_from_chars(
        total_message_characters(messages), chars_per_token=chars_per_token
    )


def resolve_token_count(usage: ContextUsage) -> int:
    if usage.provider_input_tokens is not None:
        return usage.provider_input_tokens
    return usage.estimated_input_tokens


def compaction_level(token_count: int, config: CompactionConfig) -> CompactionLevel:
    if config.context_window_tokens <= 0:
        return CompactionLevel.NONE
    ratio = token_count / config.context_window_tokens
    if ratio >= config.reset_threshold:
        return CompactionLevel.RESET
    if ratio >= config.summarize_threshold:
        return CompactionLevel.SUMMARIZE
    if ratio >= config.trim_threshold:
        return CompactionLevel.TRIM
    return CompactionLevel.NONE
