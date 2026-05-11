"""Démarrage et arrêt du gateway Marius."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from .protocol import PingEvent, decode, encode
from .workspace import pid_path, socket_path

_STARTUP_TIMEOUT = 8.0   # secondes max pour que le socket apparaisse
_PING_TIMEOUT    = 2.0   # secondes pour le ping


def is_running(agent_name: str) -> bool:
    """Vérifie si le gateway répond au ping."""
    return _ping(agent_name)


def start(agent_name: str) -> bool:
    """Lance le gateway en arrière-plan. Retourne True si démarré ou déjà actif."""
    if is_running(agent_name):
        return True

    # Nettoie un socket fantôme
    sp = socket_path(agent_name)
    if sp.exists():
        sp.unlink()

    proc = subprocess.Popen(
        [sys.executable, "-m", "marius.gateway", "--agent", agent_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Attend l'apparition du socket
    deadline = time.monotonic() + _STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if sp.exists() and _ping(agent_name):
            return True
        time.sleep(0.1)

    # Timeout — tue le processus s'il est encore en vie
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    return False


def stop(agent_name: str) -> bool:
    """Arrête le gateway via SIGTERM. Retourne True si le processus existait."""
    pp = pid_path(agent_name)
    if not pp.exists():
        return False
    try:
        pid = int(pp.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        # Attend disparition du socket (max 3s)
        deadline = time.monotonic() + 3.0
        sp = socket_path(agent_name)
        while time.monotonic() < deadline:
            if not sp.exists():
                return True
            time.sleep(0.1)
        return True
    except (ValueError, ProcessLookupError, OSError):
        return False


def restart(
    agent_name: str,
    *,
    delay_seconds: float = 1.0,
    mode: str = "auto",
) -> tuple[bool, str, dict[str, str | float]]:
    """Planifie un redémarrage sans couper le tour courant.

    Le redémarrage est délégué à un processus détaché qui attend quelques
    instants, laissant au gateway le temps de renvoyer le ToolResult et au
    modèle de formuler sa réponse finale.
    """
    selected_mode = mode if mode in ("auto", "direct", "systemd") else "auto"
    script = (
        "import sys,time\n"
        f"time.sleep({float(delay_seconds)!r})\n"
        f"agent={agent_name!r}\n"
        f"mode={selected_mode!r}\n"
        "ok=False\n"
        "if mode in ('auto','systemd'):\n"
        "    try:\n"
        "        from marius.gateway.service import agent_active_state, agent_enabled_state, is_service_installed, is_systemd_available, restart_agent\n"
        "        if is_systemd_available() and is_service_installed() and (mode == 'systemd' or agent_active_state(agent) == 'active' or agent_enabled_state(agent) == 'enabled'):\n"
        "            ok, _err = restart_agent(agent)\n"
        "    except Exception:\n"
        "        ok=False\n"
        "if not ok and mode != 'systemd':\n"
        "    try:\n"
        "        from marius.gateway.launcher import start, stop\n"
        "        stop(agent)\n"
        "        ok=start(agent)\n"
        "    except Exception:\n"
        "        ok=False\n"
        "sys.exit(0 if ok else 1)\n"
    )
    try:
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc), {"agent": agent_name, "mode": selected_mode, "delay_seconds": delay_seconds}
    return True, "", {"agent": agent_name, "mode": selected_mode, "delay_seconds": delay_seconds}


def _ping(agent_name: str) -> bool:
    """Envoie un ping au gateway. Retourne True si pong reçu."""
    sp = socket_path(agent_name)
    if not sp.exists():
        return False
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(_PING_TIMEOUT)
        conn.connect(str(sp))
        # Read welcome
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(512)
            if not chunk:
                break
            buf += chunk
        # Send ping
        conn.sendall(encode(PingEvent()))
        # Read pong
        buf2 = b""
        while b"\n" not in buf2:
            chunk = conn.recv(512)
            if not chunk:
                break
            buf2 += chunk
        line = buf2.decode(errors="replace").split("\n")[0]
        event = decode(line)
        return event.get("type") == "pong"
    except (OSError, ValueError):
        return False
    finally:
        try:
            conn.close()
        except OSError:
            pass
