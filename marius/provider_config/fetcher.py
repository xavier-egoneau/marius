"""Récupération des modèles disponibles auprès d'un provider."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .contracts import AuthType, ProviderEntry, ProviderKind
from .registry import PROVIDER_REGISTRY, normalize_base_url
from .secrets import resolve_provider_secret

_CODEX_MODELS_CACHE = Path.home() / ".codex" / "models_cache.json"

_CHATGPT_FALLBACK_MODELS = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]


class ModelFetchError(RuntimeError):
    """Erreur lors de la récupération des modèles."""


def fetch_chatgpt_oauth_models(cache_path: Path = _CODEX_MODELS_CACHE) -> list[str]:
    """Lit les modèles ChatGPT depuis le cache Codex CLI, ou retourne un fallback."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        rows: list[tuple[int, str]] = []
        for m in data.get("models", []):
            slug = str(m.get("slug") or "").strip()
            visibility = str(m.get("visibility") or "list")
            if slug and visibility in {"list", "default", ""}:
                priority = m.get("priority")
                rows.append((priority if isinstance(priority, int) else 999, slug))
        rows.sort()
        models = [slug for _, slug in rows]
        if models:
            return models
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return list(_CHATGPT_FALLBACK_MODELS)


def fetch_models(entry: ProviderEntry, *, timeout: int = 10) -> list[str]:
    """Interroge le provider et retourne la liste des modèles disponibles."""
    if entry.provider == ProviderKind.OPENAI and entry.auth_type == AuthType.AUTH:
        return fetch_chatgpt_oauth_models(cache_path=_CODEX_MODELS_CACHE)

    definition = PROVIDER_REGISTRY.get(entry.provider)
    if definition is None:
        raise ModelFetchError(f"Provider non référencé dans le registre : {entry.provider}")

    url = normalize_base_url(entry.provider, entry.base_url) + definition.models_endpoint
    req = urllib.request.Request(url)
    api_key = resolve_provider_secret(entry.api_key)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ModelFetchError(f"HTTP {exc.code} — vérifiez l'URL et la clef API") from exc
    except urllib.error.URLError as exc:
        raise ModelFetchError(f"Impossible de joindre {url} : {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ModelFetchError(
            f"L'endpoint ne renvoie pas du JSON — vérifiez que l'URL pointe vers une API compatible OpenAI (ex : https://api.example.com/v1)"
        ) from exc
    except Exception as exc:
        raise ModelFetchError(f"Erreur inattendue : {exc}") from exc

    raw_list = body.get(definition.models_list_key, [])
    models = [
        item.get(definition.model_name_key, "")
        for item in raw_list
        if isinstance(item, dict)
    ]
    models = [m for m in models if m]

    if definition.model_id_prefix_filter:
        models = [
            m for m in models
            if any(m.startswith(p) for p in definition.model_id_prefix_filter)
        ]

    return models
