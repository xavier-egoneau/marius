"""Outils de contrôle navigateur via Playwright.

Le module reste optionnel : si Playwright n'est pas installé, les outils
retournent une erreur lisible au lieu de casser le runtime.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_MAX_EXTRACT_CHARS = 20_000
_DEFAULT_TIMEOUT_MS = 15_000


def make_browser_tools(cwd: Path) -> dict[str, ToolEntry]:
    manager = _BrowserManager(cwd)
    return {
        "browser_open": ToolEntry(
            definition=ToolDefinition(
                name="browser_open",
                description=(
                    "Ouvre une URL HTTP/HTTPS dans un navigateur contrôlé par Playwright. "
                    "À utiliser seulement quand web_fetch/web_search ne suffit pas."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL HTTP/HTTPS à ouvrir."},
                        "wait_until": {
                            "type": "string",
                            "enum": ["load", "domcontentloaded", "networkidle"],
                            "description": "Moment d'attente après navigation.",
                        },
                        "timeout_ms": {"type": "integer", "description": "Timeout de navigation en millisecondes."},
                    },
                    "required": ["url"],
                },
            ),
            handler=manager.open,
        ),
        "browser_extract": ToolEntry(
            definition=ToolDefinition(
                name="browser_extract",
                description="Extrait le titre, l'URL et le texte visible de la page courante.",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Sélecteur CSS optionnel à extraire."},
                        "max_chars": {"type": "integer", "description": "Limite de caractères retournés."},
                    },
                    "required": [],
                },
            ),
            handler=manager.extract,
        ),
        "browser_screenshot": ToolEntry(
            definition=ToolDefinition(
                name="browser_screenshot",
                description="Prend une capture d'écran de la page courante et retourne le chemin de l'image.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Chemin de sortie optionnel, relatif au workspace si non absolu."},
                        "full_page": {"type": "boolean", "description": "Capture toute la page si vrai."},
                    },
                    "required": [],
                },
            ),
            handler=manager.screenshot,
        ),
        "browser_click": ToolEntry(
            definition=ToolDefinition(
                name="browser_click",
                description="Clique sur un élément de la page courante par sélecteur CSS ou texte visible.",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Sélecteur CSS à cliquer."},
                        "text": {"type": "string", "description": "Texte visible à cliquer si selector est absent."},
                    },
                    "required": [],
                },
            ),
            handler=manager.click,
        ),
        "browser_type": ToolEntry(
            definition=ToolDefinition(
                name="browser_type",
                description="Saisit du texte dans un champ de la page courante.",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Sélecteur CSS du champ."},
                        "text": {"type": "string", "description": "Texte à saisir."},
                        "press_enter": {"type": "boolean", "description": "Appuie sur Entrée après saisie."},
                    },
                    "required": ["selector", "text"],
                },
            ),
            handler=manager.type_text,
        ),
        "browser_close": ToolEntry(
            definition=ToolDefinition(
                name="browser_close",
                description="Ferme le navigateur Playwright courant.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            handler=manager.close,
        ),
    }


class _BrowserManager:
    def __init__(self, cwd: Path) -> None:
        self.cwd = Path(cwd)
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None

    def open(self, arguments: dict[str, Any]) -> ToolResult:
        url = str(arguments.get("url") or "").strip()
        if not url:
            return _error("URL manquante.", "missing_url")
        if urlparse(url).scheme not in {"http", "https"}:
            return _error("Seules les URLs http(s) sont supportées.", "unsupported_url_scheme")
        page = self._ensure_page()
        if isinstance(page, ToolResult):
            return page
        wait_until = str(arguments.get("wait_until") or "domcontentloaded")
        timeout_ms = _bounded_int(arguments.get("timeout_ms"), default=_DEFAULT_TIMEOUT_MS, minimum=1000, maximum=120_000)
        try:
            response = page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            title = page.title()
        except Exception as exc:
            return _error(f"Navigation échouée : {exc}", "navigation_failed")
        status = getattr(response, "status", None) if response is not None else None
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Page ouverte : {page.url}",
            data={"url": page.url, "title": title, "status": status},
        )

    def extract(self, arguments: dict[str, Any]) -> ToolResult:
        page = self._require_page()
        if isinstance(page, ToolResult):
            return page
        selector = str(arguments.get("selector") or "").strip()
        max_chars = _bounded_int(arguments.get("max_chars"), default=_MAX_EXTRACT_CHARS, minimum=500, maximum=100_000)
        try:
            text = page.locator(selector).inner_text(timeout=3000) if selector else page.locator("body").inner_text(timeout=3000)
            title = page.title()
        except Exception as exc:
            return _error(f"Extraction échouée : {exc}", "extract_failed")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Texte extrait : {len(text)} caractère(s){' (tronqué)' if truncated else ''}.",
            data={"url": page.url, "title": title, "selector": selector, "text": text, "truncated": truncated},
        )

    def screenshot(self, arguments: dict[str, Any]) -> ToolResult:
        page = self._require_page()
        if isinstance(page, ToolResult):
            return page
        path = self._resolve_output_path(str(arguments.get("path") or "").strip())
        full_page = bool(arguments.get("full_page", False))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=full_page)
        except Exception as exc:
            return _error(f"Capture échouée : {exc}", "screenshot_failed")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Capture navigateur enregistrée : {path}",
            data={"url": page.url, "path": str(path), "full_page": full_page},
            artifacts=[Artifact(type=ArtifactType.IMAGE, path=str(path), data={"source": "browser_screenshot"})],
        )

    def click(self, arguments: dict[str, Any]) -> ToolResult:
        page = self._require_page()
        if isinstance(page, ToolResult):
            return page
        selector = str(arguments.get("selector") or "").strip()
        text = str(arguments.get("text") or "").strip()
        if not selector and not text:
            return _error("Donne un `selector` ou un `text` à cliquer.", "missing_target")
        try:
            target = page.locator(selector).first if selector else page.get_by_text(text, exact=False).first
            target.click(timeout=5000)
        except Exception as exc:
            return _error(f"Clic échoué : {exc}", "click_failed")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            # Beaucoup de clics SPA ne déclenchent pas de navigation.
            pass
        return ToolResult(tool_call_id="", ok=True, summary=f"Clic effectué sur {selector or text}.", data={"url": page.url})

    def type_text(self, arguments: dict[str, Any]) -> ToolResult:
        page = self._require_page()
        if isinstance(page, ToolResult):
            return page
        selector = str(arguments.get("selector") or "").strip()
        text = str(arguments.get("text") or "")
        if not selector:
            return _error("Sélecteur manquant.", "missing_selector")
        try:
            locator = page.locator(selector).first
            locator.fill(text, timeout=5000)
            if bool(arguments.get("press_enter", False)):
                locator.press("Enter", timeout=5000)
        except Exception as exc:
            return _error(f"Saisie échouée : {exc}", "type_failed")
        return ToolResult(tool_call_id="", ok=True, summary=f"Texte saisi dans {selector}.", data={"url": page.url})

    def close(self, _arguments: dict[str, Any]) -> ToolResult:
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            self._page = None
            self._browser = None
            self._playwright = None
        return ToolResult(tool_call_id="", ok=True, summary="Navigateur fermé.")

    def _ensure_page(self) -> Any | ToolResult:
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError:
            return _error(
                "Playwright n'est pas installé. Installe `playwright` puis lance `python -m playwright install chromium`.",
                "playwright_missing",
            )
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page()
            return self._page
        except Exception as exc:
            return _error(f"Impossible de démarrer Chromium via Playwright : {exc}", "browser_start_failed")

    def _require_page(self) -> Any | ToolResult:
        if self._page is None:
            return _error("Aucune page ouverte. Appelle d'abord `browser_open`.", "no_page")
        return self._page

    def _resolve_output_path(self, raw_path: str) -> Path:
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = self.cwd / path
            return path
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", time.strftime("%Y%m%d-%H%M%S")).strip("-")
        return self.cwd / "browser_screenshots" / f"screenshot-{safe}.png"


def _bounded_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _error(summary: str, code: str) -> ToolResult:
    return ToolResult(tool_call_id="", ok=False, summary=summary, error=code)
