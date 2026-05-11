"""Adaptateurs HTTP concrets pour les providers LLM.

`make_adapter()` sélectionne la classe selon `ProviderDefinition.protocol`.
Ajouter un protocole = ajouter une classe ici + une valeur dans ProviderProtocol.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from marius.kernel.contracts import ContextUsage, Message, Role, ToolCall
from marius.kernel.provider import ProviderChunk, ProviderError, ProviderRequest, ProviderResponse
from marius.kernel.tool_router import ToolDefinition
from marius.provider_config.contracts import AuthType, ProviderEntry
from marius.provider_config.registry import PROVIDER_REGISTRY, ProviderProtocol
from marius.provider_config.secrets import resolve_provider_secret


def make_adapter(
    entry: ProviderEntry,
) -> "OpenAICompatibleAdapter | OllamaNativeAdapter | ChatGPTOAuthAdapter":
    """Retourne l'adapter adapté au protocol et au type d'auth déclarés."""
    defn = PROVIDER_REGISTRY.get(entry.provider)
    if defn is None:
        raise ValueError(f"Provider non référencé dans le registre : {entry.provider}")

    if defn.protocol == ProviderProtocol.OLLAMA_NATIVE:
        return OllamaNativeAdapter(entry, defn)
    if entry.auth_type == AuthType.AUTH:
        return ChatGPTOAuthAdapter(entry)
    return OpenAICompatibleAdapter(entry, defn)


class OpenAICompatibleAdapter:
    """Adapter pour tout provider utilisant le protocole OpenAI /chat/completions."""

    def __init__(self, entry: ProviderEntry, defn: Any, *, timeout: int = 120) -> None:
        self.entry = entry
        self.defn = defn
        self.timeout = timeout

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        url = self.entry.base_url.rstrip("/") + self.defn.chat_endpoint
        payload: dict[str, Any] = {
            "model": self.entry.model,
            "messages": _to_openai_messages(request.messages),
            "stream": False,
        }
        if request.tools:
            payload["tools"] = _tools_to_openai(request.tools)
            payload["tool_choice"] = "auto"

        raw = _http_post(url, payload, api_key=resolve_provider_secret(self.entry.api_key), timeout=self.timeout)

        try:
            choice = raw["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content") or ""
            finish_reason = choice.get("finish_reason", "stop")
            tool_calls = _parse_openai_tool_calls(msg.get("tool_calls") or [])
            usage_raw = raw.get("usage", {})
            usage = ContextUsage(
                estimated_input_tokens=usage_raw.get("prompt_tokens", 0),
                provider_input_tokens=usage_raw.get("prompt_tokens"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Réponse inattendue ({self.entry.provider}) : {exc}",
                provider_name=self.entry.provider,
                retryable=False,
            ) from exc

        assistant_msg = Message(
            role=Role.ASSISTANT,
            content=content,
            created_at=datetime.now(timezone.utc),
            tool_calls=tool_calls,
        )
        return ProviderResponse(
            message=assistant_msg,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            provider_name=self.entry.provider,
            model=self.entry.model,
        )


    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]:
        """Stream SSE depuis /chat/completions avec stream=true."""
        url = self.entry.base_url.rstrip("/") + self.defn.chat_endpoint
        payload: dict[str, Any] = {
            "model": self.entry.model,
            "messages": _to_openai_messages(request.messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            payload["tools"] = _tools_to_openai(request.tools)
            payload["tool_choice"] = "auto"

        pending_tool_calls: dict[int, dict[str, str]] = {}
        finish_reason = ""

        try:
            for event in _iter_sse(_http_open(url, payload, api_key=resolve_provider_secret(self.entry.api_key), timeout=self.timeout)):
                if event.get("usage"):
                    u = event["usage"]
                    yield ProviderChunk(
                        type="usage",
                        usage=ContextUsage(
                            estimated_input_tokens=u.get("prompt_tokens", 0),
                            provider_input_tokens=u.get("prompt_tokens"),
                        ),
                    )
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    finish_reason = choice.get("finish_reason") or finish_reason
                    if delta.get("content"):
                        yield ProviderChunk(type="text_delta", delta=delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index") or 0)
                        acc = pending_tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            acc["id"] += tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            acc["name"] += fn["name"]
                        if fn.get("arguments"):
                            acc["arguments"] += fn["arguments"]
        except ProviderError:
            raise

        if pending_tool_calls:
            tool_calls = []
            for idx in sorted(pending_tool_calls):
                tc = pending_tool_calls[idx]
                try:
                    arguments = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(ToolCall(id=tc["id"] or f"call_{idx}", name=tc["name"], arguments=arguments))
            yield ProviderChunk(type="tool_calls", tool_calls=tool_calls, finish_reason="tool_calls")
        else:
            yield ProviderChunk(type="done", finish_reason=finish_reason or "stop")


class OllamaNativeAdapter:
    """Adapter pour l'API Ollama native (/api/chat)."""

    def __init__(self, entry: ProviderEntry, defn: Any, *, timeout: int = 120) -> None:
        self.entry = entry
        self.defn = defn
        self.timeout = timeout

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        url = self.entry.base_url.rstrip("/") + self.defn.chat_endpoint
        payload: dict[str, Any] = {
            "model": self.entry.model,
            "messages": _to_openai_messages(request.messages),
            "stream": False,
            "think": False,
        }
        if request.tools:
            payload["tools"] = _tools_to_openai(request.tools)

        raw = _http_post(url, payload, api_key=resolve_provider_secret(self.entry.api_key), timeout=self.timeout)

        try:
            msg = raw.get("message", {})
            content = msg.get("content") or ""
            raw_tool_calls = msg.get("tool_calls") or []
            tool_calls = _parse_ollama_tool_calls(raw_tool_calls)
            finish_reason = "tool_calls" if tool_calls else "stop"
            usage = ContextUsage(
                estimated_input_tokens=raw.get("prompt_eval_count", 0),
                provider_input_tokens=raw.get("prompt_eval_count"),
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError(
                f"Réponse Ollama inattendue : {exc}",
                provider_name="ollama",
                retryable=False,
            ) from exc

        assistant_msg = Message(
            role=Role.ASSISTANT,
            content=content,
            created_at=datetime.now(timezone.utc),
            tool_calls=tool_calls,
        )
        return ProviderResponse(
            message=assistant_msg,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            provider_name=self.entry.provider,
            model=self.entry.model,
        )


    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]:
        """Stream NDJSON depuis /api/chat avec stream=true."""
        url = self.entry.base_url.rstrip("/") + self.defn.chat_endpoint
        payload: dict[str, Any] = {
            "model": self.entry.model,
            "messages": _to_openai_messages(request.messages),
            "stream": True,
            "think": False,
        }
        if request.tools:
            payload["tools"] = _tools_to_openai(request.tools)

        pending_tool_calls: list[dict[str, Any]] = []

        try:
            for chunk in _iter_ndjson(_http_open(url, payload, api_key=resolve_provider_secret(self.entry.api_key), timeout=self.timeout)):
                msg = chunk.get("message") or {}
                if msg.get("content"):
                    yield ProviderChunk(type="text_delta", delta=msg["content"])
                for tc in msg.get("tool_calls") or []:
                    pending_tool_calls.append(tc)
                if chunk.get("done"):
                    yield ProviderChunk(
                        type="usage",
                        usage=ContextUsage(
                            estimated_input_tokens=chunk.get("prompt_eval_count", 0),
                            provider_input_tokens=chunk.get("prompt_eval_count"),
                        ),
                    )
        except ProviderError:
            raise

        if pending_tool_calls:
            tool_calls = _parse_ollama_tool_calls(pending_tool_calls)
            yield ProviderChunk(type="tool_calls", tool_calls=tool_calls, finish_reason="tool_calls")
        else:
            yield ProviderChunk(type="done", finish_reason="stop")


# ── ChatGPT OAuth adapter ────────────────────────────────────────────────────

_CHATGPT_BASE_URL = "https://chatgpt.com/backend-api/codex"


class ChatGPTOAuthAdapter:
    """Adapter pour ChatGPT via OAuth PKCE — Responses API (backend-api/codex)."""

    def __init__(self, entry: ProviderEntry, *, timeout: int = 120) -> None:
        self.entry = entry
        self.timeout = timeout

    # ── public interface ──────────────────────────────────────────────────────

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Non-streaming : accumule les chunks du stream."""
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = ContextUsage()

        for chunk in self.stream(request):
            if chunk.type == "text_delta" and chunk.delta:
                content_parts.append(chunk.delta)
            elif chunk.type == "tool_calls":
                tool_calls.extend(chunk.tool_calls)
            elif chunk.type == "usage" and chunk.usage:
                usage = ContextUsage(
                    estimated_input_tokens=chunk.usage.get("input_tokens", 0),
                    provider_input_tokens=chunk.usage.get("input_tokens"),
                )

        return ProviderResponse(
            message=Message(
                role=Role.ASSISTANT,
                content="".join(content_parts),
                created_at=datetime.now(timezone.utc),
                tool_calls=tool_calls,
            ),
            usage=usage,
        )

    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]:
        url = f"{_CHATGPT_BASE_URL}/responses"
        system, input_messages = _split_system(request.messages)

        payload: dict[str, Any] = {
            "model": self.entry.model,
            "input": _to_chatgpt_input(input_messages),
            "instructions": system,
            "stream": True,
            "store": False,
        }
        if request.tools:
            payload["tools"] = _to_chatgpt_tools(request.tools)

        pending_tool_calls: list[dict[str, Any]] = []
        saw_text_delta = False

        try:
            response = _http_open_headers(url, payload, headers=_chatgpt_headers(resolve_provider_secret(self.entry.api_key)), timeout=self.timeout)
        except ProviderError:
            raise

        for event in _iter_sse(response):
            event_type = event.get("type")

            if event_type == "response.output_text.delta":
                delta = event.get("delta") or ""
                if delta:
                    saw_text_delta = True
                    yield ProviderChunk(type="text_delta", delta=delta)

            elif event_type == "response.output_text.done":
                text = event.get("text") or ""
                if text and not saw_text_delta:
                    saw_text_delta = True
                    yield ProviderChunk(type="text_delta", delta=text)

            elif event_type == "response.output_item.done":
                item = event.get("item") or {}
                call = _normalize_chatgpt_tool_call(item)
                if call is not None:
                    pending_tool_calls.append(call)
                else:
                    text = _chatgpt_text_from_item(item)
                    if text and not saw_text_delta:
                        saw_text_delta = True
                        yield ProviderChunk(type="text_delta", delta=text)

            elif event_type == "response.completed":
                response_data = event.get("response") or {}
                completed_text = _chatgpt_text_from_response(response_data)
                if completed_text and not saw_text_delta:
                    saw_text_delta = True
                    yield ProviderChunk(type="text_delta", delta=completed_text)
                usage_raw = response_data.get("usage") or {}
                if usage_raw:
                    yield ProviderChunk(
                        type="usage",
                        usage={
                            "input_tokens": int(usage_raw.get("input_tokens") or 0),
                            "output_tokens": int(usage_raw.get("output_tokens") or 0),
                        },
                    )
                calls = _chatgpt_tool_calls_from_response(response_data) or pending_tool_calls
                if calls:
                    yield ProviderChunk(
                        type="tool_calls",
                        tool_calls=[
                            ToolCall(id=c["id"], name=c["name"], arguments=c["arguments"])
                            for c in calls
                        ],
                        finish_reason="tool_calls",
                    )
                    return
                yield ProviderChunk(type="done", finish_reason="stop")
                return

            elif event_type == "response.failed":
                error = event.get("error") or {}
                raise ProviderError(
                    f"ChatGPT : {error.get('message') or 'provider_error'}",
                    provider_name="chatgpt_oauth",
                    retryable=False,
                )


# ── helpers ChatGPT ───────────────────────────────────────────────────────────


def _chatgpt_headers(token: str) -> dict[str, str]:
    import base64
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
    }
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        auth_claim = data.get("https://api.openai.com/auth", {})
        account_id = auth_claim.get("chatgpt_account_id") or auth_claim.get("user_id", "")
        if account_id:
            headers["chatgpt-account-id"] = account_id
    except Exception:
        pass
    return headers


def _split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    """Sépare le message SYSTEM (instructions) des messages conversationnels."""
    system_parts: list[str] = []
    rest: list[Message] = []
    for msg in messages:
        if msg.role == Role.SYSTEM:
            system_parts.append(msg.content)
        else:
            rest.append(msg)
    return "\n\n".join(system_parts), rest


def _to_chatgpt_input(messages: list[Message]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    open_call_ids: set[str] = set()
    for msg in messages:
        if msg.role == Role.TOOL:
            call_id = msg.correlation_id or ""
            if call_id in open_call_ids:
                result.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": msg.content,
                })
                open_call_ids.discard(call_id)
            elif msg.content:
                result.append({
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": f"Résultat d'outil précédent :\n{msg.content}",
                    }],
                })
        elif msg.tool_calls:
            for tc in msg.tool_calls:
                open_call_ids.add(tc.id)
                result.append({
                    "type": "function_call",
                    "call_id": tc.id,
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                })
        elif msg.role in (Role.USER, Role.ASSISTANT):
            content_type = "output_text" if msg.role == Role.ASSISTANT else "input_text"
            if msg.content:
                result.append({
                    "type": "message",
                    "role": msg.role.value,
                    "content": [{"type": content_type, "text": msg.content}],
                })
    return result


def _to_chatgpt_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in tools
    ]


def _normalize_chatgpt_tool_call(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "function_call":
        return None
    name = item.get("name") or ""
    call_id = item.get("call_id") or item.get("id") or ""
    if not name or not call_id:
        return None
    arguments = item.get("arguments") or "{}"
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    return {"id": call_id, "name": name, "arguments": arguments}


def _chatgpt_tool_calls_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for item in response.get("output") or []:
        call = _normalize_chatgpt_tool_call(item)
        if call is not None:
            calls.append(call)
    return calls


def _chatgpt_text_from_response(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("output") or []:
        text = _chatgpt_text_from_item(item)
        if text:
            parts.append(text)
    return "".join(parts)


def _chatgpt_text_from_item(item: dict[str, Any]) -> str:
    if item.get("type") != "message":
        return ""
    parts: list[str] = []
    for content in item.get("content") or []:
        if not isinstance(content, dict):
            continue
        if content.get("type") in {"output_text", "text"}:
            text = content.get("text") or ""
            if text:
                parts.append(text)
    return "".join(parts)


def _http_open_headers(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: int = 120,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            _http_error_message(exc, url),
            provider_name=url,
            retryable=exc.code in {429, 500, 502, 503, 504},
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(
            f"Impossible de joindre {url} : {exc.reason}",
            provider_name=url,
            retryable=True,
        ) from exc
    except Exception as exc:
        raise ProviderError(f"Erreur inattendue : {exc}", provider_name=url, retryable=False) from exc


# ── conversion messages ───────────────────────────────────────────────────────

_ROLE_MAP = {
    Role.SYSTEM:    "system",
    Role.USER:      "user",
    Role.ASSISTANT: "assistant",
    Role.TOOL:      "tool",
}


def _to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        role = _ROLE_MAP.get(msg.role)
        if role is None:
            continue

        if msg.role == Role.TOOL:
            result.append({
                "role": "tool",
                "tool_call_id": msg.correlation_id,
                "content": msg.content,
            })
        elif msg.tool_calls:
            result.append({
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
        else:
            result.append({"role": role, "content": msg.content})

    return result


# ── conversion outils ─────────────────────────────────────────────────────────


def _tools_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _parse_openai_tool_calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
    calls = []
    for item in raw:
        fn = item.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(
            id=item.get("id") or f"call_{len(calls)}",
            name=name,
            arguments=arguments,
        ))
    return calls


def _parse_ollama_tool_calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
    calls = []
    for i, item in enumerate(raw):
        fn = item.get("function", {})
        name = fn.get("name", "")
        arguments = fn.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        calls.append(ToolCall(
            id=f"ollama_call_{i}",
            name=name,
            arguments=arguments,
        ))
    return calls


# ── HTTP ──────────────────────────────────────────────────────────────────────


def _http_open(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str = "",
    timeout: int = 120,
) -> Any:
    """Ouvre une connexion HTTP et retourne la réponse brute (file-like).

    Le caller est responsable de fermer la connexion (utiliser un context manager).
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            _http_error_message(exc, url),
            provider_name=url,
            retryable=exc.code in {429, 500, 502, 503, 504},
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(
            f"Impossible de joindre {url} : {exc.reason}",
            provider_name=url,
            retryable=True,
        ) from exc
    except Exception as exc:
        raise ProviderError(f"Erreur inattendue : {exc}", provider_name=url, retryable=False) from exc


def _iter_sse(response: Any) -> Iterator[dict[str, Any]]:
    """Parcourt une réponse SSE et yield les objets JSON des events data:."""
    with response:
        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue


def _iter_ndjson(response: Any) -> Iterator[dict[str, Any]]:
    """Parcourt une réponse NDJSON et yield les objets JSON ligne par ligne."""
    with response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _http_post(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            _http_error_message(exc, url),
            provider_name=url,
            retryable=exc.code in {429, 500, 502, 503, 504},
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(
            f"Impossible de joindre {url} : {exc.reason}",
            provider_name=url,
            retryable=True,
        ) from exc
    except Exception as exc:
        raise ProviderError(
            f"Erreur inattendue : {exc}",
            provider_name=url,
            retryable=False,
        ) from exc


def _http_error_message(exc: urllib.error.HTTPError, url: str) -> str:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        detail = ""
    if len(detail) > 800:
        detail = detail[:799] + "…"
    return f"HTTP {exc.code} sur {url}" + (f" — {detail}" if detail else "")
