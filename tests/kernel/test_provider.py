from __future__ import annotations

from datetime import datetime

from marius.kernel.contracts import ContextUsage, Message, Role
from marius.kernel.provider import (
    InMemoryProviderAdapter,
    ProviderConfig,
    ProviderError,
    ProviderRequest,
)


def test_in_memory_provider_returns_structured_response() -> None:
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="test", model="stub-model"),
        completion_text="Réponse provider",
        usage=ContextUsage(provider_input_tokens=42, max_context_tokens=1000),
    )
    request = ProviderRequest(
        messages=[
            Message(
                role=Role.USER,
                content="Bonjour",
                created_at=datetime(2026, 5, 7, 15, 30, 0),
            )
        ],
        metadata={"session_id": "canon"},
    )

    response = provider.generate(request)

    assert response.message.role is Role.ASSISTANT
    assert response.message.content == "Réponse provider"
    assert response.usage.provider_input_tokens == 42
    assert response.provider_name == "test"
    assert response.model == "stub-model"


def test_in_memory_provider_can_raise_normalized_error() -> None:
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="test", model="stub-model"),
        error=ProviderError("provider unavailable", provider_name="test", retryable=True),
    )

    try:
        provider.generate(ProviderRequest(messages=[]))
    except ProviderError as exc:
        assert exc.provider_name == "test"
        assert exc.retryable is True
    else:
        raise AssertionError("provider error should be raised")
