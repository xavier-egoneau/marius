"""Contrats centraux du kernel Marius.

Ce module porte uniquement des objets de domaine réutilisables.
Il ne connaît ni Telegram, ni le web, ni la CLI comme surfaces concrètes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL = "tool"


class ArtifactType(str, Enum):
    DIFF = "diff"
    IMAGE = "image"
    REPORT = "report"
    FILE = "file"


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(slots=True)
class Artifact:
    type: ArtifactType
    path: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Message:
    role: Role
    content: str
    created_at: datetime
    correlation_id: str = ""
    visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    tool_call_id: str
    ok: bool | None
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class ContextUsage:
    estimated_input_tokens: int = 0
    provider_input_tokens: int | None = None
    max_context_tokens: int | None = None


@dataclass(slots=True)
class CompactionNotice:
    level: str
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
