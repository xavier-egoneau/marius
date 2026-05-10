"""Diagnostic de l'installation Marius."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"
_VALID_PERMISSION_MODES = {"safe", "limited", "power"}


@dataclass
class Check:
    label: str
    ok: bool
    hint: str = ""
    warning: bool = False   # True = non bloquant (jaune)


@dataclass
class Section:
    title: str
    checks: list[Check] = field(default_factory=list)


def run_doctor(agent_name: str | None = None) -> list[Section]:
    """Exécute tous les diagnostics et retourne les sections."""
    sections: list[Section] = []
    sections.append(_check_config(agent_name))
    sections.append(_check_provider(agent_name))
    sections.append(_check_searxng())
    sections.append(_check_files())
    sections.append(_check_gateway(agent_name))
    return sections


# ── sections ─────────────────────────────────────────────────────────────────

def _check_config(agent_name: str | None) -> Section:
    from marius.config.store import ConfigStore
    s = Section("Config")

    cfg_path = _MARIUS_HOME / "config.json"
    if not cfg_path.exists():
        s.checks.append(Check("config.json", False, "absent — lance `marius setup`"))
        return s
    s.checks.append(Check("config.json", True))

    store = ConfigStore()
    cfg = store.load()
    if cfg is None:
        s.checks.append(Check("config.json lisible", False, "JSON invalide — relance `marius setup`"))
        return s

    mode = cfg.permission_mode
    mode_ok = mode in _VALID_PERMISSION_MODES
    s.checks.append(Check(
        f"Permission mode : {mode}",
        mode_ok,
        f"valeur inconnue ({mode!r}) — attendu safe/limited/power",
    ))

    name = agent_name or cfg.main_agent or "main"
    agent = cfg.agents.get(name)
    if agent is None:
        s.checks.append(Check(f"Agent '{name}'", False, f"non configuré — lance `marius config`"))
    else:
        s.checks.append(Check(f"Agent '{name}' ({agent.provider_id} / {agent.model})", True))
        if not agent.tools:
            s.checks.append(Check("Outils configurés", False, "liste vide", warning=True))

    return s


def _check_provider(agent_name: str | None) -> Section:
    from marius.config.store import ConfigStore
    from marius.provider_config.store import ProviderStore
    from marius.provider_config.fetcher import ModelFetchError, fetch_models
    s = Section("Provider")

    cfg = ConfigStore().load()
    if cfg is None:
        s.checks.append(Check("Config chargée", False, "config.json manquant ou invalide"))
        return s

    name = agent_name or cfg.main_agent or "main"
    agent = cfg.agents.get(name)
    if agent is None:
        s.checks.append(Check("Agent trouvé", False, f"agent '{name}' absent de config.json"))
        return s

    providers = ProviderStore().load()
    entry = next((p for p in providers if p.id == agent.provider_id), None)
    if entry is None:
        s.checks.append(Check(
            f"Provider '{agent.provider_id}'",
            False,
            "non référencé — lance `marius add provider`",
        ))
        return s
    s.checks.append(Check(f"Provider '{entry.name}' enregistré", True))

    try:
        models = fetch_models(entry)
        s.checks.append(Check(f"Connexion provider ({len(models)} modèles)", True))
        if agent.model not in models:
            s.checks.append(Check(
                f"Modèle '{agent.model}' disponible",
                False,
                f"non trouvé — liste : {', '.join(models[:5])}{'…' if len(models) > 5 else ''}",
                warning=True,
            ))
        else:
            s.checks.append(Check(f"Modèle '{agent.model}' disponible", True))
    except ModelFetchError as exc:
        s.checks.append(Check("Connexion provider", False, str(exc)))

    return s


def _check_searxng() -> Section:
    s = Section("SearxNG")

    docker_ok = _command_exists("docker")
    s.checks.append(Check(
        "Docker installé",
        docker_ok,
        "non trouvé — web_search nécessite Docker",
        warning=not docker_ok,
    ))

    url = os.environ.get("MARIUS_SEARCH_URL", "http://localhost:19080")
    reachable = _check_url(url)
    hint = "" if reachable else f"non joignable — docker compose -f docker-compose.searxng.yml up -d"
    s.checks.append(Check(f"SearxNG ({url})", reachable, hint, warning=not reachable))

    return s


def _check_files() -> Section:
    s = Section("Fichiers système")

    soul = _MARIUS_HOME / "SOUL.md"
    s.checks.append(Check(
        "SOUL.md",
        soul.exists(),
        f"absent ({soul}) — crée le pour personnaliser l'identité de l'agent",
        warning=True,
    ))

    agents_md = _MARIUS_HOME / "AGENTS.md"
    s.checks.append(Check(
        "AGENTS.md",
        agents_md.exists(),
        "absent — conventions globales facultatives",
        warning=True,
    ))

    skills_dir = _MARIUS_HOME / "skills"
    if skills_dir.exists():
        skill_count = sum(1 for p in skills_dir.iterdir() if p.is_dir())
        s.checks.append(Check(f"Skills ({skill_count} installé(s))", True))
    else:
        s.checks.append(Check("Dossier skills", False, f"absent ({skills_dir})", warning=True))

    return s


def _check_gateway(agent_name: str | None) -> Section:
    from marius.config.store import ConfigStore
    from marius.gateway.workspace import pid_path, socket_path
    s = Section("Gateway")

    cfg = ConfigStore().load()
    name = agent_name or (cfg.main_agent if cfg else None) or "main"

    pid_file = pid_path(name)
    sock_file = socket_path(name)

    if not pid_file.exists():
        s.checks.append(Check(
            f"Gateway '{name}'",
            False,
            "non actif — lance `marius gateway start`",
            warning=True,
        ))
        return s

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        s.checks.append(Check(f"Gateway '{name}' (PID illisible)", False, hint=str(pid_file), warning=True))
        return s

    alive = _pid_alive(pid)
    if alive:
        s.checks.append(Check(f"Gateway '{name}' actif (PID {pid})", True))
    else:
        s.checks.append(Check(
            f"Gateway '{name}' (PID {pid} mort)",
            False,
            "pid file obsolète — redémarre avec `marius gateway start`",
            warning=True,
        ))

    sock_ok = sock_file.exists()
    if not sock_ok:
        s.checks.append(Check("Socket Unix", False, f"absent ({sock_file})", warning=True))

    return s


# ── helpers ───────────────────────────────────────────────────────────────────

def _command_exists(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_url(url: str) -> bool:
    try:
        from urllib.request import urlopen
        with urlopen(url, timeout=3):
            return True
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── affichage ─────────────────────────────────────────────────────────────────

def format_report_text(sections: list[Section]) -> tuple[str, int]:
    """Retourne (texte brut, nb_erreurs) — pour les canaux sans Rich."""
    lines: list[str] = ["🩺 marius doctor\n"]
    errors = 0
    warnings = 0
    for sec in sections:
        lines.append(f"{sec.title}")
        for chk in sec.checks:
            if chk.ok:
                mark = "✓"
            elif chk.warning:
                mark = "!"
                warnings += 1
            else:
                mark = "✗"
                errors += 1
            line = f"  {mark} {chk.label}"
            if not chk.ok and chk.hint:
                line += f"\n    → {chk.hint}"
            lines.append(line)
        lines.append("")

    if errors == 0 and warnings == 0:
        lines.append("Tout est en ordre.")
    else:
        parts = []
        if errors:
            parts.append(f"{errors} erreur(s) bloquante(s)")
        if warnings:
            parts.append(f"{warnings} avertissement(s)")
        lines.append(", ".join(parts) + ".")

    return "\n".join(lines), errors


def print_report(sections: list[Section]) -> int:
    """Affiche le rapport avec Rich. Retourne le nombre d'erreurs bloquantes."""
    from rich.console import Console
    from rich.rule import Rule

    c = Console(highlight=False)
    c.print()
    c.print(Rule("[bold]marius doctor[/]"))
    c.print()

    errors = 0
    warnings = 0

    for sec in sections:
        c.print(f"[bold]{sec.title}[/]")
        for chk in sec.checks:
            if chk.ok:
                mark = "[green]✓[/]"
            elif chk.warning:
                mark = "[yellow]![/]"
                warnings += 1
            else:
                mark = "[red]✗[/]"
                errors += 1
            line = f"  {mark} {chk.label}"
            if not chk.ok and chk.hint:
                line += f"\n      [dim]→ {chk.hint}[/]"
            c.print(line)
        c.print()

    if errors == 0 and warnings == 0:
        c.print("[green]Tout est en ordre.[/]")
    else:
        parts = []
        if errors:
            parts.append(f"[red]{errors} erreur(s) bloquante(s)[/]")
        if warnings:
            parts.append(f"[yellow]{warnings} avertissement(s)[/]")
        c.print(", ".join(parts) + ".")

    c.print()
    return errors
