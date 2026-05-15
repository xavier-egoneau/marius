"""Provider configuration tools.

These tools write the existing ProviderStore. They refuse raw secret values and
accept only secret references for API keys.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from marius.config.store import ConfigStore
from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.provider_config.contracts import AuthType, ProviderEntry
from marius.provider_config.fetcher import ModelFetchError, fetch_models
from marius.provider_config.registry import PROVIDER_REGISTRY, normalize_base_url, requires_api_key_for_base_url
from marius.provider_config.secrets import public_secret_label
from marius.provider_config.store import ProviderStore

_RAW_SECRET_KEYS = ("api_key", "token", "secret", "password", "value", "raw_api_key")


def make_provider_admin_tools(
    *,
    provider_path: Path | None = None,
    config_path: Path | None = None,
    model_fetcher: Callable[[ProviderEntry], list[str]] | None = None,
) -> dict[str, ToolEntry]:
    store = ProviderStore(path=provider_path) if provider_path is not None else ProviderStore()
    config_store = ConfigStore(path=config_path) if config_path is not None else ConfigStore()
    fetcher = model_fetcher or fetch_models

    def provider_list(arguments: dict[str, Any]) -> ToolResult:
        providers = store.load()
        lines = [f"Providers: {len(providers)} configured."]
        for entry in providers:
            secret_label = public_secret_label(entry.api_key)
            secret = f", key={secret_label}" if secret_label else ""
            lines.append(f"- {entry.id}: {entry.name} ({entry.provider}/{entry.auth_type}), model={entry.model}{secret}")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={"providers": [_provider_data(entry) for entry in providers]},
        )

    def provider_save(arguments: dict[str, Any]) -> ToolResult:
        if any(key in arguments for key in _RAW_SECRET_KEYS):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Raw provider secrets are refused. Use `api_key_ref` as env:NAME, file:/path or secret:NAME.",
                error="raw_secret_refused",
            )
        entries = store.load()
        existing = _find_provider(entries, provider_id=_optional_text(arguments.get("id")), name=_optional_text(arguments.get("name")))
        name = _optional_text(arguments.get("name")) or (existing.name if existing else "")
        if not name:
            return ToolResult(tool_call_id="", ok=False, summary="`name` is required.", error="missing_name")

        provider = _optional_text(arguments.get("provider")) or (existing.provider if existing else "")
        if provider not in PROVIDER_REGISTRY:
            return ToolResult(tool_call_id="", ok=False, summary=f"Unknown provider: {provider}", error="unknown_provider")
        defn = PROVIDER_REGISTRY[provider]

        auth_type = _optional_text(arguments.get("auth_type")) or (existing.auth_type if existing else AuthType.API)
        if auth_type not in defn.supported_auth_types:
            return ToolResult(tool_call_id="", ok=False, summary=f"Unsupported auth_type for {provider}: {auth_type}", error="unsupported_auth_type")

        base_url = normalize_base_url(
            provider,
            _optional_text(arguments.get("base_url")) or (existing.base_url if existing else defn.default_base_url),
        )
        model = _optional_text(arguments.get("model")) or (existing.model if existing else "")
        api_key_ref = _optional_text(arguments.get("api_key_ref"))
        api_key = api_key_ref if api_key_ref is not None else (existing.api_key if existing else "")
        if auth_type == AuthType.API and requires_api_key_for_base_url(provider, base_url) and not api_key:
            return ToolResult(tool_call_id="", ok=False, summary="`api_key_ref` is required for this provider.", error="missing_api_key_ref")
        if api_key_ref is not None and not api_key_ref.startswith(("env:", "file:", "secret:")):
            return ToolResult(tool_call_id="", ok=False, summary="`api_key_ref` must be env:NAME, file:/path or secret:NAME.", error="invalid_api_key_ref")

        metadata = dict(existing.metadata) if existing else {}
        if isinstance(arguments.get("metadata"), dict):
            metadata.update(arguments["metadata"])
        entry = ProviderEntry(
            id=existing.id if existing else (_optional_text(arguments.get("id")) or ProviderEntry.generate_id()),
            name=name,
            provider=provider,
            auth_type=auth_type,
            base_url=base_url,
            api_key=api_key,
            model=model,
            added_at=existing.added_at if existing else datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
        if existing:
            store.update(entry)
            created = False
        else:
            store.add(entry)
            created = True
        verb = "created" if created else "updated"
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Provider {verb}: {entry.name} ({entry.id}).",
            data={"provider": _provider_data(entry), "created": created},
        )

    def provider_delete(arguments: dict[str, Any]) -> ToolResult:
        provider_id = _optional_text(arguments.get("id"))
        name = _optional_text(arguments.get("name"))
        entry = _find_provider(store.load(), provider_id=provider_id, name=name)
        if entry is None:
            return ToolResult(tool_call_id="", ok=False, summary="Provider not found.", error="provider_not_found")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Deletion requires `confirm: true`.", error="confirmation_required")
        users = _agents_using_provider(config_store, entry.id)
        if users and not bool(arguments.get("force", False)):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Provider is used by agent(s): {', '.join(users)}. Pass `force: true` to delete anyway.",
                error="provider_in_use",
                data={"agents": users},
            )
        store.delete(entry.id)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Provider deleted: {entry.name} ({entry.id}).",
            data={"deleted": _provider_data(entry), "agents_using_provider": users},
        )

    def provider_models(arguments: dict[str, Any]) -> ToolResult:
        entry = _find_provider(
            store.load(),
            provider_id=_optional_text(arguments.get("id")),
            name=_optional_text(arguments.get("name")),
        )
        if entry is None:
            return ToolResult(tool_call_id="", ok=False, summary="Provider not found.", error="provider_not_found")
        try:
            models = fetcher(entry)
        except ModelFetchError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc), error="model_fetch_failed")
        except Exception as exc:
            return ToolResult(tool_call_id="", ok=False, summary=f"Unexpected model fetch error: {exc}", error="model_fetch_failed")
        limit = _bounded_int(arguments.get("limit"), default=50, minimum=1, maximum=200)
        shown = models[:limit]
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Provider models for {entry.name}: {len(shown)} shown / {len(models)} available.",
            data={"provider": _provider_data(entry), "models": shown, "total": len(models)},
        )

    return {
        "provider_list": ToolEntry(
            definition=ToolDefinition(
                name="provider_list",
                description="List configured LLM providers without exposing raw API keys.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            handler=provider_list,
        ),
        "provider_save": ToolEntry(
            definition=ToolDefinition(
                name="provider_save",
                description="Create or update a provider using api_key_ref, never a raw API key.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "provider": {"type": "string", "description": "Provider kind, e.g. openai or ollama."},
                        "auth_type": {"type": "string", "description": "api or auth."},
                        "base_url": {"type": "string"},
                        "model": {"type": "string"},
                        "api_key_ref": {"type": "string", "description": "env:NAME, file:/path or secret:NAME."},
                        "metadata": {"type": "object"},
                    },
                    "required": ["name"],
                },
            ),
            handler=provider_save,
        ),
        "provider_delete": ToolEntry(
            definition=ToolDefinition(
                name="provider_delete",
                description="Delete a configured provider after confirmation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "confirm": {"type": "boolean"},
                        "force": {"type": "boolean"},
                    },
                    "required": ["confirm"],
                },
            ),
            handler=provider_delete,
        ),
        "provider_models": ToolEntry(
            definition=ToolDefinition(
                name="provider_models",
                description="Fetch model names from a configured provider.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": [],
                },
            ),
            handler=provider_models,
        ),
    }


_DEFAULT_TOOLS = make_provider_admin_tools()
PROVIDER_LIST = _DEFAULT_TOOLS["provider_list"]
PROVIDER_SAVE = _DEFAULT_TOOLS["provider_save"]
PROVIDER_DELETE = _DEFAULT_TOOLS["provider_delete"]
PROVIDER_MODELS = _DEFAULT_TOOLS["provider_models"]


def _provider_data(entry: ProviderEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        "provider": entry.provider,
        "auth_type": entry.auth_type,
        "base_url": entry.base_url,
        "model": entry.model,
        "has_api_key": bool(entry.api_key),
        "api_key_ref": public_secret_label(entry.api_key),
        "added_at": entry.added_at,
        "metadata": dict(entry.metadata),
    }


def _find_provider(entries: list[ProviderEntry], *, provider_id: str | None, name: str | None) -> ProviderEntry | None:
    if provider_id:
        for entry in entries:
            if entry.id == provider_id:
                return entry
    if name:
        matches = [entry for entry in entries if entry.name == name]
        if len(matches) == 1:
            return matches[0]
    return None


def _agents_using_provider(config_store: ConfigStore, provider_id: str) -> list[str]:
    cfg = config_store.load()
    if cfg is None:
        return []
    return sorted(name for name, agent in cfg.agents.items() if agent.provider_id == provider_id)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))
