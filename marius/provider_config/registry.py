"""Registre des providers supportés.

Ajouter un provider = ajouter une entrée dans PROVIDER_REGISTRY.
Ajouter un nouveau protocole = ajouter une classe dans adapters/http_provider.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from .contracts import AuthType, ProviderKind


class ProviderProtocol(str, Enum):
    """Protocole HTTP utilisé pour les appels de complétion."""
    OPENAI_COMPATIBLE = "openai_compatible"  # POST /chat/completions
    OLLAMA_NATIVE     = "ollama_native"       # POST /api/chat


class ContextWindowStrategy(str, Enum):
    """Stratégie pour résoudre la fenêtre de contexte d'un modèle."""
    STATIC     = "static"      # valeur connue dans _STATIC_CONTEXT_WINDOWS
    API        = "api"         # endpoint dédié du provider (ex: Ollama /api/show)
    WEB_SEARCH = "web_search"  # futur : demander au modèle de chercher sur le web
    FALLBACK   = "fallback"    # 128k par défaut si rien d'autre ne fonctionne


@dataclass(frozen=True)
class ProviderDefinition:
    kind: str
    label: str
    default_base_url: str
    requires_api_key: bool
    # ── découverte des modèles ──
    models_endpoint: str
    models_list_key: str
    model_name_key: str
    supported_auth_types: tuple[str, ...]
    # ── complétion ──
    protocol: ProviderProtocol
    chat_endpoint: str
    # ── fenêtre de contexte ──
    context_window_strategy: ContextWindowStrategy
    context_window_api_endpoint: str = ""   # utilisé si strategy == API
    # ── filtres ──
    model_id_prefix_filter: tuple[str, ...] = field(default_factory=tuple)


PROVIDER_REGISTRY: dict[str, ProviderDefinition] = {
    ProviderKind.OPENAI: ProviderDefinition(
        kind=ProviderKind.OPENAI,
        label="ChatGPT / OpenAI",
        default_base_url="https://api.openai.com/v1",
        requires_api_key=True,
        models_endpoint="/models",
        models_list_key="data",
        model_name_key="id",
        supported_auth_types=(AuthType.AUTH, AuthType.API),
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        chat_endpoint="/chat/completions",
        context_window_strategy=ContextWindowStrategy.STATIC,
        model_id_prefix_filter=("gpt-", "o1", "o3", "o4"),
    ),
    ProviderKind.OLLAMA: ProviderDefinition(
        kind=ProviderKind.OLLAMA,
        label="Ollama (local)",
        default_base_url="http://localhost:11434",
        requires_api_key=False,
        models_endpoint="/api/tags",
        models_list_key="models",
        model_name_key="name",
        supported_auth_types=(AuthType.API,),
        protocol=ProviderProtocol.OLLAMA_NATIVE,
        chat_endpoint="/api/chat",
        context_window_strategy=ContextWindowStrategy.API,
        context_window_api_endpoint="/api/show",
    ),
}


def normalize_base_url(provider: str, base_url: str) -> str:
    """Normalise l'URL racine d'un provider sans casser les endpoints compatibles.

    Pour l'API officielle OpenAI, l'utilisateur saisit souvent
    `https://api.openai.com`. Le protocole OpenAI-compatible de Marius attend une
    base qui inclut `/v1`, sinon `/models` et `/chat/completions` pointent sur un
    endpoint inexistant.
    """
    definition = PROVIDER_REGISTRY.get(provider)
    raw = str(base_url or (definition.default_base_url if definition else "")).strip().rstrip("/")
    if not raw:
        return raw
    parsed = urlparse(raw)
    if provider == ProviderKind.OPENAI and parsed.netloc == "api.openai.com" and parsed.path in {"", "/"}:
        return raw + "/v1"
    if provider == ProviderKind.OLLAMA and parsed.path.rstrip("/") == "/api":
        return raw[: -len("/api")]
    return raw


def requires_api_key_for_base_url(provider: str, base_url: str) -> bool:
    """Retourne si cette configuration nécessite une clé API."""
    definition = PROVIDER_REGISTRY.get(provider)
    if definition and definition.requires_api_key:
        return True
    parsed = urlparse(normalize_base_url(provider, base_url))
    return provider == ProviderKind.OLLAMA and parsed.netloc == "ollama.com"
