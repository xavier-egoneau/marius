"""Compaction du contexte interne.

Le moteur de compaction réduit la pression de contexte sans détruire
l'historique visible utilisateur, qui relève d'une autre couche.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


def estimate_tokens_from_chars(char_count: int, *, chars_per_token: int = 4) -> int:
    """Approximation simple tant qu'aucun tokenizer dédié n'est branché."""
    if char_count <= 0:
        return 0
    return max(1, char_count // max(chars_per_token, 1))


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
