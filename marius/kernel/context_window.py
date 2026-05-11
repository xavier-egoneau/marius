"""Résolution de la fenêtre de contexte d'un modèle LLM.

Brique standalone : aucune dépendance réseau, aucune dépendance provider.
L'appel réseau éventuel (stratégie API) est injecté via `api_resolver`.

Stratégies :
  STATIC     → registre statique par slug de modèle
  API        → délégué à `api_resolver` (callable injecté par la couche adapter)
  WEB_SEARCH → futur : demander au modèle de chercher sur le web
  FALLBACK   → 128 000 tokens par défaut
"""

from __future__ import annotations

from collections.abc import Callable

FALLBACK_CONTEXT_WINDOW = 128_000

# Valeurs publiques connues — providers compatibles OpenAI et autres.
_STATIC_CONTEXT_WINDOWS: dict[str, int] = {
    # OpenAI GPT-5.x
    "gpt-5.5":             1_000_000,
    "gpt-5.4":               250_000,
    "gpt-5.4-mini":          250_000,
    "gpt-5.3-codex":         250_000,
    "gpt-5.3-codex-spark":   250_000,
    "gpt-5.2":               250_000,
    "gpt-5":               1_000_000,
    # OpenAI GPT-4.x
    "gpt-4o":                128_000,
    "gpt-4o-mini":           128_000,
    "gpt-4-turbo":           128_000,
    "gpt-4-turbo-preview":   128_000,
    "gpt-4":                   8_192,
    # OpenAI GPT-3.x
    "gpt-3.5-turbo":          16_385,
    # OpenAI o-series
    "o1":                    200_000,
    "o1-mini":               128_000,
    "o1-preview":            128_000,
    "o3":                    200_000,
    "o3-mini":               200_000,
    "o4-mini":               200_000,
}


def resolve_static(model: str) -> int | None:
    """Cherche la fenêtre dans le registre statique.

    Essaie d'abord une correspondance exacte, puis par préfixe pour couvrir
    les variantes versionées (ex : gpt-4o-2024-05-13 → gpt-4o = 128k).
    """
    exact = _STATIC_CONTEXT_WINDOWS.get(model)
    if exact is not None:
        return exact
    for slug, window in _STATIC_CONTEXT_WINDOWS.items():
        if model.startswith(slug):
            return window
    return None


def resolve_context_window(
    model: str,
    strategy: str,
    *,
    api_resolver: Callable[[], int | None] | None = None,
) -> int:
    """Résout la fenêtre de contexte selon la stratégie déclarée.

    `api_resolver` est un callable sans argument qui retourne la fenêtre
    ou None. Il est fourni par la couche adapter quand strategy == API,
    ce qui garde cette brique indépendante de tout accès réseau.

    Retourne toujours un entier positif (FALLBACK_CONTEXT_WINDOW au minimum).
    """
    if strategy == "static":
        result = resolve_static(model)
        if result is not None:
            return result

    elif strategy == "api":
        if api_resolver is not None:
            result = api_resolver()
            if result is not None:
                return result
        # Filet de sécurité : tente le registre statique même en stratégie API
        result = resolve_static(model)
        if result is not None:
            return result

    elif strategy == "web_search":
        # Non encore implémenté.
        # Quand la recherche web sera disponible, cette branche demandera
        # au modèle de chercher la valeur sur le web.
        pass

    return FALLBACK_CONTEXT_WINDOW
