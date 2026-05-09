"""Configuration du canal Telegram.

Stockée dans ~/.marius/telegram.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"
_CONFIG_PATH  = _MARIUS_HOME / "telegram.json"


@dataclass
class TelegramChannelConfig:
    token: str
    agent_name: str = "main"
    allowed_users: list[int] = field(default_factory=list)   # vide = tous
    allowed_chats: list[int] = field(default_factory=list)   # vide = tous les DM
    enabled: bool = True


def config_path() -> Path:
    return _CONFIG_PATH


def load() -> TelegramChannelConfig | None:
    if not _CONFIG_PATH.exists():
        return None
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return TelegramChannelConfig(
            token=raw["token"],
            agent_name=raw.get("agent_name", "main"),
            allowed_users=[int(u) for u in raw.get("allowed_users", [])],
            allowed_chats=[int(c) for c in raw.get("allowed_chats", [])],
            enabled=bool(raw.get("enabled", True)),
        )
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return None


def save(cfg: TelegramChannelConfig) -> None:
    _MARIUS_HOME.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_configured() -> bool:
    return _CONFIG_PATH.exists()
