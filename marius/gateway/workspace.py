"""Chemins et initialisation du workspace par agent."""

from __future__ import annotations

from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"
_WORKSPACE_ROOT = _MARIUS_HOME / "workspace"
_RUN_DIR = _MARIUS_HOME / "run"


def workspace_dir(agent_name: str) -> Path:
    return _WORKSPACE_ROOT / agent_name


def memory_db_path(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "memory.db"


def sessions_dir(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "sessions"


def socket_path(agent_name: str) -> Path:
    return _RUN_DIR / f"{agent_name}.sock"


def pid_path(agent_name: str) -> Path:
    return _RUN_DIR / f"{agent_name}.pid"


def lock_path(agent_name: str) -> Path:
    return _RUN_DIR / f"{agent_name}.lock"


def web_pid_path(agent_name: str, port: int) -> Path:
    return _RUN_DIR / f"web_{agent_name}_{int(port)}.pid"


def jobs_path(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "jobs.json"


def telegram_offset_path(agent_name: str) -> Path:
    return _RUN_DIR / f"telegram_{agent_name}.offset"


def web_history_path(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "web_history.json"


def web_conversations_dir(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "web_conversations"


def reminders_path(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "reminders.json"


def daily_cache_path(agent_name: str) -> Path:
    return workspace_dir(agent_name) / "daily_latest.md"


def ensure_workspace(agent_name: str) -> Path:
    """Crée les dossiers du workspace si nécessaires. Retourne le workspace dir."""
    ws = workspace_dir(agent_name)
    ws.mkdir(parents=True, exist_ok=True)
    sessions_dir(agent_name).mkdir(exist_ok=True)
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    return ws
