from __future__ import annotations

from marius.kernel.context_window import (
    FALLBACK_CONTEXT_WINDOW,
    resolve_context_window,
    resolve_static,
)
from marius.provider_config.registry import ContextWindowStrategy


# ── resolve_static ────────────────────────────────────────────────────────────


def test_resolve_static_exact_match():
    assert resolve_static("gpt-4o") == 128_000


def test_resolve_static_exact_match_gpt54():
    assert resolve_static("gpt-5.4") == 250_000


def test_resolve_static_prefix_match():
    # variante versionée non listée → match par préfixe
    assert resolve_static("gpt-4o-2024-05-13") == 128_000


def test_resolve_static_unknown_returns_none():
    assert resolve_static("unknown-model-xyz") is None


def test_resolve_static_o_series():
    assert resolve_static("o1") == 200_000
    assert resolve_static("o3") == 200_000


# ── resolve_context_window ────────────────────────────────────────────────────


def test_resolve_context_window_static_known_model():
    result = resolve_context_window("gpt-4o", ContextWindowStrategy.STATIC)
    assert result == 128_000


def test_resolve_context_window_static_unknown_falls_back():
    result = resolve_context_window("totally-unknown", ContextWindowStrategy.STATIC)
    assert result == FALLBACK_CONTEXT_WINDOW


def test_resolve_context_window_api_strategy_uses_resolver():
    result = resolve_context_window(
        "llama3",
        ContextWindowStrategy.API,
        api_resolver=lambda: 65_536,
    )
    assert result == 65_536


def test_resolve_context_window_api_falls_back_to_static_when_resolver_returns_none():
    result = resolve_context_window(
        "gpt-4o",
        ContextWindowStrategy.API,
        api_resolver=lambda: None,
    )
    # resolver None → static fallback → gpt-4o = 128k
    assert result == 128_000


def test_resolve_context_window_api_falls_back_to_fallback_when_resolver_and_static_miss():
    result = resolve_context_window(
        "totally-unknown-model",
        ContextWindowStrategy.API,
        api_resolver=lambda: None,
    )
    assert result == FALLBACK_CONTEXT_WINDOW


def test_resolve_context_window_web_search_falls_back():
    result = resolve_context_window("any-model", ContextWindowStrategy.WEB_SEARCH)
    assert result == FALLBACK_CONTEXT_WINDOW


def test_resolve_context_window_fallback_strategy():
    result = resolve_context_window("any-model", ContextWindowStrategy.FALLBACK)
    assert result == FALLBACK_CONTEXT_WINDOW
