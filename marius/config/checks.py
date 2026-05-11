"""Helpers de vérification d'environnement partagés entre wizard et doctor."""

from __future__ import annotations

import subprocess


def command_exists(cmd: str) -> bool:
    """Retourne True si la commande est disponible dans le PATH."""
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_url(url: str) -> bool:
    """Retourne True si l'URL répond en moins de 3 secondes."""
    try:
        from urllib.request import urlopen
        with urlopen(url, timeout=3):
            return True
    except Exception:
        return False
