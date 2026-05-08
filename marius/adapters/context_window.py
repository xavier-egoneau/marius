"""Résolution de la fenêtre de contexte via appel réseau au provider.

Complément de kernel/context_window.py pour la stratégie API.
Standalone : dépend uniquement de urllib (stdlib).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable


def resolve_via_api(
    base_url: str,
    api_endpoint: str,
    model: str,
    *,
    api_key: str = "",
    timeout: int = 5,
) -> int | None:
    """Interroge l'endpoint dédié du provider pour récupérer la fenêtre de contexte.

    Supporte le format Ollama (/api/show → modelinfo["llama.context_length"]).
    Retourne None si l'appel échoue ou si la clé est absente.
    """
    url = base_url.rstrip("/") + api_endpoint
    body = json.dumps({"name": model}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None

    model_info = data.get("modelinfo") or {}
    for key, value in model_info.items():
        if "context_length" in key and isinstance(value, int) and value > 0:
            return value
    return None


def make_api_resolver(
    base_url: str,
    api_endpoint: str,
    model: str,
    *,
    api_key: str = "",
    timeout: int = 5,
) -> Callable[[], int | None]:
    """Retourne un callable sans argument pour injection dans resolve_context_window."""
    def _resolve() -> int | None:
        return resolve_via_api(
            base_url, api_endpoint, model,
            api_key=api_key, timeout=timeout,
        )
    return _resolve
