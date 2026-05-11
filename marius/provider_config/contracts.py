"""Contrats de la brique provider_config.

Standalone : aucune dépendance vers le reste de Marius.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuthType(str, Enum):
    AUTH = "auth"
    API = "api"


class ProviderKind(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class ProviderEntry:
    """Un provider configuré, sérialisable en JSON."""

    id: str
    name: str
    provider: str
    auth_type: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate_id(cls) -> str:
        return str(uuid.uuid4())[:8]
