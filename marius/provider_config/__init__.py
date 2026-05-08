"""Brique standalone de configuration des providers LLM."""

from .contracts import AuthType, ProviderEntry, ProviderKind
from .fetcher import ModelFetchError, fetch_models
from .registry import PROVIDER_REGISTRY, ProviderDefinition
from .store import ProviderStore

__all__ = [
    "AuthType",
    "ModelFetchError",
    "PROVIDER_REGISTRY",
    "ProviderDefinition",
    "ProviderEntry",
    "ProviderKind",
    "ProviderStore",
    "fetch_models",
]
