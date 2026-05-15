from __future__ import annotations

import json
from datetime import datetime

from marius.adapters.http_provider import ChatGPTOAuthAdapter, OllamaNativeAdapter, OpenAICompatibleAdapter, _to_chatgpt_input, _to_openai_messages, _to_ollama_messages
from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolCall, ToolResult
from marius.kernel.provider import ProviderRequest
from marius.kernel.session import SessionRuntime
from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.provider_config.registry import PROVIDER_REGISTRY


class _SSE:
    def __init__(self, events: list[dict]) -> None:
        self._lines = [
            f"data: {json.dumps(event)}\n".encode("utf-8")
            for event in events
        ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)


def _entry() -> ProviderEntry:
    return ProviderEntry(
        id="p1",
        name="chatgpt",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.AUTH,
        api_key="header.payload.signature",
        model="gpt-5.4",
    )


def _api_entry() -> ProviderEntry:
    return ProviderEntry(
        id="p2",
        name="openai-api",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        base_url="https://api.openai.com",
        api_key="sk-test",
        model="gpt-4o",
    )


def _ollama_cloud_entry() -> ProviderEntry:
    return ProviderEntry(
        id="p3",
        name="ollama-cloud",
        provider=ProviderKind.OLLAMA,
        auth_type=AuthType.API,
        base_url="https://ollama.com/api",
        api_key="ollama-test",
        model="gpt-oss:120b",
    )


def _request() -> ProviderRequest:
    return ProviderRequest(
        messages=[
            Message(
                role=Role.USER,
                content="hey",
                created_at=datetime(2026, 5, 9, 10, 0, 0),
            )
        ]
    )


def test_openai_compatible_adapter_normalizes_official_root_url(monkeypatch):
    seen: list[str] = []

    def fake_post(url, payload, *, api_key, timeout):
        seen.append(url)
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("marius.adapters.http_provider._http_post", fake_post)

    adapter = OpenAICompatibleAdapter(_api_entry(), PROVIDER_REGISTRY[ProviderKind.OPENAI])
    response = adapter.generate(_request())

    assert seen == ["https://api.openai.com/v1/chat/completions"]
    assert response.message.content == "ok"


def test_ollama_native_adapter_accepts_cloud_api_base_url(monkeypatch):
    seen: list[str] = []

    def fake_post(url, payload, *, api_key, timeout):
        seen.append(url)
        return {"message": {"content": "ok"}, "done": True}

    monkeypatch.setattr("marius.adapters.http_provider._http_post", fake_post)

    adapter = OllamaNativeAdapter(_ollama_cloud_entry(), PROVIDER_REGISTRY[ProviderKind.OLLAMA])
    response = adapter.generate(_request())

    assert seen == ["https://ollama.com/api/chat"]
    assert response.message.content == "ok"


def test_openai_messages_include_user_image_artifacts(tmp_path):
    image = tmp_path / "demo.png"
    image.write_bytes(b"png bytes")
    message = Message(
        role=Role.USER,
        content="analyse ça",
        created_at=datetime(2026, 5, 9, 10, 0, 0),
        artifacts=[Artifact(type=ArtifactType.IMAGE, path=str(image), data={"mime_type": "image/png"})],
    )

    result = _to_openai_messages([message])

    assert result[0]["role"] == "user"
    assert result[0]["content"][0] == {"type": "text", "text": "analyse ça"}
    assert result[0]["content"][1]["type"] == "image_url"
    assert result[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_ollama_messages_include_user_image_artifacts(tmp_path):
    image = tmp_path / "demo.jpg"
    image.write_bytes(b"jpg bytes")
    message = Message(
        role=Role.USER,
        content="analyse ça",
        created_at=datetime(2026, 5, 9, 10, 0, 0),
        artifacts=[Artifact(type=ArtifactType.IMAGE, path=str(image), data={"mime_type": "image/jpeg"})],
    )

    result = _to_ollama_messages([message])

    assert result[0]["role"] == "user"
    assert result[0]["content"] == "analyse ça"
    assert result[0]["images"]


def test_chatgpt_stream_reads_text_from_completed_response(monkeypatch):
    events = [
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Salut !"}],
                    }
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        }
    ]
    monkeypatch.setattr("marius.adapters.http_provider._http_open_headers", lambda *a, **k: _SSE(events))

    chunks = list(ChatGPTOAuthAdapter(_entry()).stream(_request()))

    assert "".join(c.delta for c in chunks if c.type == "text_delta") == "Salut !"
    assert [c.type for c in chunks] == ["text_delta", "usage", "done"]


def test_chatgpt_stream_does_not_duplicate_completed_text_after_deltas(monkeypatch):
    events = [
        {"type": "response.output_text.delta", "delta": "Sa"},
        {"type": "response.output_text.delta", "delta": "lut !"},
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Salut !"}],
                    }
                ],
            },
        },
    ]
    monkeypatch.setattr("marius.adapters.http_provider._http_open_headers", lambda *a, **k: _SSE(events))

    chunks = list(ChatGPTOAuthAdapter(_entry()).stream(_request()))

    assert "".join(c.delta for c in chunks if c.type == "text_delta") == "Salut !"


def test_chatgpt_stream_reads_output_text_done_when_no_delta(monkeypatch):
    events = [
        {"type": "response.output_text.done", "text": "Bonjour."},
        {"type": "response.completed", "response": {}},
    ]
    monkeypatch.setattr("marius.adapters.http_provider._http_open_headers", lambda *a, **k: _SSE(events))

    chunks = list(ChatGPTOAuthAdapter(_entry()).stream(_request()))

    assert "".join(c.delta for c in chunks if c.type == "text_delta") == "Bonjour."


def test_chatgpt_stream_reads_text_from_output_item_done(monkeypatch):
    events = [
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Texte final."}],
            },
        },
        {"type": "response.completed", "response": {}},
    ]
    monkeypatch.setattr("marius.adapters.http_provider._http_open_headers", lambda *a, **k: _SSE(events))

    chunks = list(ChatGPTOAuthAdapter(_entry()).stream(_request()))

    assert "".join(c.delta for c in chunks if c.type == "text_delta") == "Texte final."


def test_chatgpt_stream_emits_tool_calls_without_trailing_done(monkeypatch):
    events = [
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_123",
                "name": "list_dir",
                "arguments": "{\"path\":\".\"}",
            },
        },
        {"type": "response.completed", "response": {}},
    ]
    monkeypatch.setattr("marius.adapters.http_provider._http_open_headers", lambda *a, **k: _SSE(events))

    chunks = list(ChatGPTOAuthAdapter(_entry()).stream(_request()))

    assert [c.type for c in chunks] == ["tool_calls"]
    assert chunks[0].finish_reason == "tool_calls"
    assert chunks[0].tool_calls[0].id == "call_123"


def test_chatgpt_input_keeps_tool_output_after_matching_call():
    messages = [
        Message(
            role=Role.ASSISTANT,
            content="",
            created_at=datetime(2026, 5, 9, 10, 0, 0),
            tool_calls=[ToolCall(id="call_123", name="list_dir", arguments={"path": "."})],
        ),
        Message(
            role=Role.TOOL,
            content="README.md",
            created_at=datetime(2026, 5, 9, 10, 0, 1),
            correlation_id="call_123",
        ),
    ]

    result = _to_chatgpt_input(messages)

    assert result[0]["type"] == "function_call"
    assert result[1] == {
        "type": "function_call_output",
        "call_id": "call_123",
        "output": "README.md",
    }


def test_chatgpt_input_downgrades_orphan_tool_output_to_text_message():
    messages = [
        Message(
            role=Role.USER,
            content="résume",
            created_at=datetime(2026, 5, 9, 10, 0, 0),
        ),
        Message(
            role=Role.TOOL,
            content="ROADMAP.md",
            created_at=datetime(2026, 5, 9, 10, 0, 1),
            correlation_id="call_previous",
        ),
    ]

    result = _to_chatgpt_input(messages)

    assert result[1]["type"] == "message"
    assert result[1]["role"] == "user"
    assert "Résultat d'outil précédent" in result[1]["content"][0]["text"]


def test_chatgpt_input_includes_user_image_artifacts(tmp_path):
    image = tmp_path / "demo.webp"
    image.write_bytes(b"webp bytes")
    messages = [
        Message(
            role=Role.USER,
            content="regarde",
            created_at=datetime(2026, 5, 9, 10, 0, 0),
            artifacts=[Artifact(type=ArtifactType.IMAGE, path=str(image), data={"mime_type": "image/webp"})],
        )
    ]

    result = _to_chatgpt_input(messages)

    assert result[0]["content"][0] == {"type": "input_text", "text": "regarde"}
    assert result[0]["content"][1]["type"] == "input_image"
    assert result[0]["content"][1]["image_url"].startswith("data:image/webp;base64,")


def test_chatgpt_input_from_session_history_has_no_orphan_function_call_output():
    session = SessionRuntime(session_id="test")
    turn = session.start_turn(
        user_message=Message(
            role=Role.USER,
            content="explore",
            created_at=datetime(2026, 5, 9, 10, 0, 0),
        )
    )
    session.attach_tool_result(
        turn.id,
        ToolResult(tool_call_id="call_previous", ok=True, summary="ROADMAP.md"),
    )
    session.finish_turn(
        turn.id,
        assistant_message=Message(
            role=Role.ASSISTANT,
            content="J'ai exploré.",
            created_at=datetime(2026, 5, 9, 10, 0, 2),
        ),
    )

    messages = session.internal_messages(include_tool_results=True)
    result = _to_chatgpt_input(messages)

    assert all(item["type"] != "function_call_output" for item in result)
    assert any(
        item["type"] == "message"
        and item["role"] == "user"
        and "ROADMAP.md" in item["content"][0]["text"]
        for item in result
    )
