"""Best-effort lifecycle helper for the local SearxNG backend."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

DEFAULT_SEARCH_URL = "http://localhost:19080"


@dataclass(frozen=True)
class SearxngStartResult:
    ok: bool
    status: str
    url: str
    compose_file: str = ""
    detail: str = ""


def ensure_searxng_started(
    *,
    url: str | None = None,
    compose_file: Path | None = None,
    timeout_seconds: float = 10.0,
) -> SearxngStartResult:
    """Ensure the bundled SearxNG service is reachable.

    This is deliberately best-effort. Marius should not crash if Docker or the
    compose file is unavailable; `web_search` will still return a clear tool
    error if the backend cannot be reached.
    """
    search_url = (url or os.environ.get("MARIUS_SEARCH_URL") or DEFAULT_SEARCH_URL).rstrip("/")
    if _url_ok(search_url):
        return SearxngStartResult(ok=True, status="already_running", url=search_url)

    if os.environ.get("MARIUS_SEARCH_AUTO_START", "").strip().lower() in {"0", "false", "no", "off"}:
        return SearxngStartResult(ok=False, status="disabled", url=search_url)

    if search_url != DEFAULT_SEARCH_URL:
        return SearxngStartResult(
            ok=False,
            status="custom_url_unreachable",
            url=search_url,
            detail="auto-start is only available for the bundled local SearxNG service",
        )

    compose = Path(compose_file) if compose_file is not None else find_compose_file()
    if compose is None:
        return SearxngStartResult(ok=False, status="compose_missing", url=search_url)

    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose), "up", "-d"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return SearxngStartResult(
            ok=False,
            status="start_failed",
            url=search_url,
            compose_file=str(compose),
            detail=str(exc),
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _url_ok(search_url):
            return SearxngStartResult(ok=True, status="started", url=search_url, compose_file=str(compose))
        time.sleep(0.5)

    return SearxngStartResult(
        ok=False,
        status="not_ready",
        url=search_url,
        compose_file=str(compose),
        detail=f"SearxNG did not respond within {timeout_seconds:g}s",
    )


def find_compose_file() -> Path | None:
    candidates: list[Path] = []
    here = Path(__file__).resolve()
    candidates.extend(parent / "docker-compose.searxng.yml" for parent in here.parents)
    candidates.extend(parent / "docker-compose.searxng.yml" for parent in Path.cwd().resolve().parents)
    candidates.append(Path.cwd().resolve() / "docker-compose.searxng.yml")
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return None


def _url_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=3):
            return True
    except Exception:
        return False

