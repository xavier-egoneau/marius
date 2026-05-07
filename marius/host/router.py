"""Entrées host normalisées pour les canaux concrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InboundRequest:
    channel: str
    session_id: str
    peer_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboundPayload:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
