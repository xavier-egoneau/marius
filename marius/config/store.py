"""Lecture et écriture de ~/.marius/config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import AgentConfig, DEFAULT_TOOLS, MariusConfig

_MARIUS_HOME = Path.home() / ".marius"
DEFAULT_CONFIG_PATH = _MARIUS_HOME / "config.json"
_PRE_VISION_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "run_bash",
    "web_fetch",
    "web_search",
    "skill_view",
]


class ConfigStore:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> MariusConfig | None:
        if not self.path.exists():
            return None
        try:
            raw: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            return _from_dict(raw)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def save(self, config: MariusConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(_to_dict(config), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _to_dict(config: MariusConfig) -> dict[str, Any]:
    return {
        "permission_mode": config.permission_mode,
        "main_agent": config.main_agent,
        "agents": {
            name: {
                "name": agent.name,
                "provider_id": agent.provider_id,
                "model": agent.model,
                "tools": agent.tools,
                "skills": agent.skills,
            }
            for name, agent in config.agents.items()
        },
    }


def _from_dict(raw: dict[str, Any]) -> MariusConfig:
    agents = {
        name: AgentConfig(
            name=data["name"],
            provider_id=data["provider_id"],
            model=data["model"],
            tools=_normalize_tools(data.get("tools")),
            skills=data.get("skills", []),
        )
        for name, data in raw.get("agents", {}).items()
    }
    return MariusConfig(
        permission_mode=raw.get("permission_mode", "limited"),
        main_agent=raw.get("main_agent", "main"),
        agents=agents,
    )


def _normalize_tools(raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, list):
        return list(DEFAULT_TOOLS)
    tools = [str(tool) for tool in raw_tools]
    if tools == _PRE_VISION_DEFAULT_TOOLS:
        return list(DEFAULT_TOOLS)
    return tools
