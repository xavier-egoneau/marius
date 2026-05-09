"""Gestion du service systemd pour le gateway Marius.

Installe un service template dans ~/.config/systemd/user/.
Chaque agent correspond à une instance : marius-gateway@<nom>.service

Commandes systemd équivalentes :
    systemctl --user enable --now marius-gateway@main
    systemctl --user status marius-gateway@main
    systemctl --user disable --now marius-gateway@main
    loginctl enable-linger   # pour démarrer sans session active
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_SERVICE_TEMPLATE = "marius-gateway@.service"
_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


# ── génération du fichier service ─────────────────────────────────────────────


def _unit_content() -> str:
    python = sys.executable
    home   = str(Path.home())
    return (
        "[Unit]\n"
        "Description=Marius Gateway (%i)\n"
        "After=default.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={python} -m marius.gateway --agent %i\n"
        "Restart=on-failure\n"
        "RestartSec=10s\n"
        f"Environment=HOME={home}\n"
        f"WorkingDirectory={home}\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "SyslogIdentifier=marius-gateway-%i\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


# ── API publique ──────────────────────────────────────────────────────────────


def is_systemd_available() -> bool:
    """Vérifie que systemctl est disponible sur le système."""
    return shutil.which("systemctl") is not None


def is_service_installed() -> bool:
    """Vérifie que le fichier template est installé."""
    return (_SYSTEMD_USER_DIR / _SERVICE_TEMPLATE).exists()


def install_service() -> Path:
    """Écrit le fichier template et recharge le daemon. Retourne le chemin."""
    _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    path = _SYSTEMD_USER_DIR / _SERVICE_TEMPLATE
    path.write_text(_unit_content(), encoding="utf-8")
    _daemon_reload()
    return path


def uninstall_service(*, stop_all: bool = True) -> None:
    """Supprime le fichier template (et arrête tous les agents si demandé)."""
    path = _SYSTEMD_USER_DIR / _SERVICE_TEMPLATE
    if path.exists():
        path.unlink()
    _daemon_reload()


def enable_agent(agent_name: str) -> tuple[bool, str]:
    """Active le service pour un agent (démarre maintenant + au login).

    Retourne (succès, message_erreur).
    """
    r = _systemctl("enable", "--now", f"marius-gateway@{agent_name}.service")
    return r.returncode == 0, r.stderr.strip()


def disable_agent(agent_name: str) -> tuple[bool, str]:
    """Désactive le service pour un agent (arrête + retire du login)."""
    r = _systemctl("disable", "--now", f"marius-gateway@{agent_name}.service")
    return r.returncode == 0, r.stderr.strip()


def agent_active_state(agent_name: str) -> str:
    """Retourne l'état systemd de l'agent : active, inactive, failed, unknown."""
    if not is_systemd_available():
        return "unknown"
    r = _systemctl("is-active", f"marius-gateway@{agent_name}")
    return r.stdout.strip() or "unknown"


def agent_enabled_state(agent_name: str) -> str:
    """Retourne si le service est activé au démarrage : enabled, disabled, unknown."""
    if not is_systemd_available():
        return "unknown"
    r = _systemctl("is-enabled", f"marius-gateway@{agent_name}")
    return r.stdout.strip() or "unknown"


def linger_hint() -> str | None:
    """Retourne la commande loginctl à exécuter si le linger n'est pas actif.

    Sans linger, le service ne démarre pas sans session ouverte.
    """
    import os
    user = os.environ.get("USER", "")
    if not user or not is_systemd_available():
        return None
    r = subprocess.run(
        ["loginctl", "show-user", user, "--property=Linger"],
        capture_output=True, text=True,
    )
    if "Linger=yes" in r.stdout:
        return None
    return f"loginctl enable-linger {user}"


# ── helpers ───────────────────────────────────────────────────────────────────


def _daemon_reload() -> None:
    if is_systemd_available():
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
        )


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
    )
