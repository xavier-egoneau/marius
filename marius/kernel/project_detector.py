"""Détection de la nature d'un répertoire : projet ou dossier trop large.

Brique standalone — aucune dépendance externe ni réseau.
Utilisée par guardian_policy pour affiner les décisions d'extension d'allow.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ProjectSignal(str, Enum):
    STRONG   = "strong"    # .git ou fichier de projet reconnu → projet certain
    MODERATE = "moderate"  # fichier de build générique       → probablement un projet
    WEAK     = "weak"      # marqueur léger (README, .env…)   → possiblement un projet
    NONE     = "none"      # aucun marqueur détecté           → demander confirmation
    DENIED   = "denied"    # chemin système ou trop large      → refus inconditionnel


@dataclass(frozen=True)
class ProjectDetectionResult:
    signal: ProjectSignal
    markers_found: list[str]
    path: Path

    @property
    def is_project(self) -> bool:
        return self.signal in (ProjectSignal.STRONG, ProjectSignal.MODERATE, ProjectSignal.WEAK)

    @property
    def is_denied(self) -> bool:
        return self.signal is ProjectSignal.DENIED


# ── registres de marqueurs ────────────────────────────────────────────────────

# Fichiers/dossiers → présence suffisante pour conclure à un projet
_STRONG_EXACT: frozenset[str] = frozenset({
    ".git",
    # Python
    "pyproject.toml", "setup.py", "setup.cfg",
    # JavaScript / TypeScript
    "package.json",
    # Rust
    "Cargo.toml",
    # Go
    "go.mod",
    # Java / Kotlin (Maven)
    "pom.xml",
    # PHP
    "composer.json",
    # Ruby
    "Gemfile",
    # Elixir
    "mix.exs",
    # Dart / Flutter
    "pubspec.yaml",
    # Swift Package Manager
    "Package.swift",
})

# Extensions de fichiers → scan du répertoire (moins fréquents)
_STRONG_EXTENSIONS: frozenset[str] = frozenset({
    ".sln",          # .NET solution
    ".xcodeproj",    # Xcode
    ".xcworkspace",
})

_MODERATE_EXACT: frozenset[str] = frozenset({
    "Makefile", "makefile", "GNUmakefile",
    "Dockerfile",
    "CMakeLists.txt",
    "build.gradle", "build.gradle.kts",
    "requirements.txt",
    "Pipfile",
    "setup.cfg",
    ".travis.yml",
    "Jenkinsfile",
    "tox.ini",
})

_MODERATE_EXTENSIONS: frozenset[str] = frozenset({
    ".csproj",       # .NET project
    ".vcxproj",      # Visual C++
})

_WEAK_EXACT: frozenset[str] = frozenset({
    "AGENTS.md",
    "CLAUDE.md",
    "README.md", "README.rst", "README.txt",
    ".github",
    "docker-compose.yml", "docker-compose.yaml",
    ".env",
    ".editorconfig",
    ".gitignore",
})

# ── chemins système à refuser inconditionnellement ────────────────────────────

def _build_system_sets() -> tuple[frozenset[Path], tuple[Path, ...]]:
    """Construit les ensembles de chemins système selon la plateforme courante."""
    if sys.platform == "win32":
        systemroot = os.environ.get("SYSTEMROOT", "C:\\Windows")
        programfiles = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        programfiles_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        programdata = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")

        exact_strs = [
            "C:\\", "C:\\Users", "C:\\Windows",
            systemroot, programfiles, programfiles_x86, programdata,
        ]
        prefix_strs = [
            systemroot, programfiles, programfiles_x86, programdata,
        ]
        if appdata:
            prefix_strs.append(appdata)
        if localappdata:
            prefix_strs.append(localappdata)

        exact   = frozenset(Path(p) for p in exact_strs if p)
        prefixes = tuple(Path(p) for p in prefix_strs if p)
    else:
        exact = frozenset(
            Path(p) for p in (
                "/", "/bin", "/sbin", "/lib", "/lib64",
                "/usr", "/usr/bin", "/usr/lib",
                "/etc", "/var", "/var/log",
                "/sys", "/proc", "/dev", "/run", "/boot", "/tmp",
                # macOS
                "/System", "/Library", "/Applications",
                "/private", "/private/etc", "/private/var", "/private/tmp",
            )
        )
        prefixes = (
            Path("/usr"),
            Path("/etc"),
            Path("/var"),
            Path("/sys"),
            Path("/proc"),
            Path("/System"),
            Path("/Library"),
            Path("/Applications"),
            Path("/private"),
        )

    return exact, prefixes


_SYSTEM_EXACT, _SYSTEM_PREFIXES = _build_system_sets()


# ── logique de détection ──────────────────────────────────────────────────────


def detect_project(path: Path) -> ProjectDetectionResult:
    """Évalue si `path` est un projet ou un dossier trop large / système.

    Retourne toujours un résultat — ne lève jamais d'exception.
    """
    try:
        resolved = path.expanduser().resolve()
    except (OSError, RuntimeError):
        return ProjectDetectionResult(
            signal=ProjectSignal.DENIED,
            markers_found=[],
            path=path,
        )

    # 1 — chemins système inconditionnels
    if _is_system_path(resolved):
        return ProjectDetectionResult(
            signal=ProjectSignal.DENIED,
            markers_found=[],
            path=resolved,
        )

    # 2 — profondeur trop faible (≤ 3 sur Unix : /, home, username)
    #     La home de l'utilisateur est exclue en plus
    if len(resolved.parts) <= 3 or resolved == Path.home():
        return ProjectDetectionResult(
            signal=ProjectSignal.DENIED,
            markers_found=[],
            path=resolved,
        )

    # 3 — liste les entrées du répertoire (une seule fois)
    try:
        entries: set[str] = {e.name for e in os.scandir(resolved)}
        entry_exts: set[str] = {
            os.path.splitext(name)[1].lower()
            for name in entries
            if os.path.splitext(name)[1]
        }
    except (PermissionError, NotADirectoryError, OSError):
        return ProjectDetectionResult(
            signal=ProjectSignal.NONE,
            markers_found=[],
            path=resolved,
        )

    # 4 — signaux forts
    strong = sorted(
        (_STRONG_EXACT & entries)
        | {ext for ext in _STRONG_EXTENSIONS if ext in entry_exts}
    )
    if strong:
        return ProjectDetectionResult(
            signal=ProjectSignal.STRONG,
            markers_found=strong,
            path=resolved,
        )

    # 5 — signaux modérés
    moderate = sorted(
        (_MODERATE_EXACT & entries)
        | {ext for ext in _MODERATE_EXTENSIONS if ext in entry_exts}
    )
    if moderate:
        return ProjectDetectionResult(
            signal=ProjectSignal.MODERATE,
            markers_found=moderate,
            path=resolved,
        )

    # 6 — signaux faibles
    weak = sorted(_WEAK_EXACT & entries)
    if weak:
        return ProjectDetectionResult(
            signal=ProjectSignal.WEAK,
            markers_found=weak,
            path=resolved,
        )

    return ProjectDetectionResult(
        signal=ProjectSignal.NONE,
        markers_found=[],
        path=resolved,
    )


def _is_system_path(path: Path) -> bool:
    if path in _SYSTEM_EXACT:
        return True
    for prefix in _SYSTEM_PREFIXES:
        try:
            path.relative_to(prefix)
            return True
        except ValueError:
            pass
    return False
