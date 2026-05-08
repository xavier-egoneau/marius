"""Outil vision local via Ollama.

Standalone : dépend uniquement des contrats tool/kernel et de la stdlib.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "gemma4"
_DEFAULT_PROMPT = "Décris précisément cette image et relève les éléments utiles pour répondre à l'utilisateur."
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _vision(arguments: dict[str, Any]) -> ToolResult:
    path_str = arguments.get("path", "")
    prompt = (arguments.get("prompt") or _DEFAULT_PROMPT).strip()
    model = (arguments.get("model") or os.environ.get("MARIUS_VISION_MODEL") or _DEFAULT_MODEL).strip()
    base_url = (os.environ.get("MARIUS_VISION_OLLAMA_URL") or _DEFAULT_BASE_URL).rstrip("/")

    if not path_str:
        return ToolResult(tool_call_id="", ok=False, summary="Argument `path` manquant.", error="missing_arg:path")
    if not model:
        return ToolResult(tool_call_id="", ok=False, summary="Modèle vision manquant.", error="missing_model")

    path = Path(path_str).expanduser()
    mime_type = mimetypes.guess_type(path.name)[0]
    if mime_type not in _SUPPORTED_MIME_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_MIME_TYPES))
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Format image non supporté : {mime_type or 'inconnu'} ({supported}).",
            error="unsupported_image_type",
        )

    try:
        image_bytes = path.read_bytes()
    except FileNotFoundError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Image introuvable : {path}", error="file_not_found")
    except PermissionError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Permission refusée : {path}", error="permission_denied")

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Image trop volumineuse : {len(image_bytes)} octets.",
            error="image_too_large",
        )

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image_bytes).decode("ascii")],
            }
        ],
    }

    try:
        raw = _http_post(f"{base_url}/api/chat", payload)
    except urllib.error.HTTPError as exc:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Ollama a refusé l'analyse vision (HTTP {exc.code}).",
            error=f"http_error:{exc.code}",
        )
    except urllib.error.URLError as exc:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Ollama vision injoignable ({base_url}) : {exc.reason}",
            error="ollama_unreachable",
        )
    except Exception as exc:
        return ToolResult(tool_call_id="", ok=False, summary=f"Erreur vision : {exc}", error=str(exc))

    try:
        content = (raw.get("message") or {}).get("content") or ""
    except AttributeError:
        content = ""
    if not content.strip():
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary="Réponse Ollama vision vide.",
            error="empty_vision_response",
            data={"model": model, "path": str(path)},
        )

    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=content.strip(),
        data={
            "path": str(path),
            "model": model,
            "base_url": base_url,
            "prompt": prompt,
            "mime_type": mime_type,
        },
        artifacts=[Artifact(type=ArtifactType.IMAGE, path=str(path))],
    )


def _http_post(url: str, payload: dict[str, Any], *, timeout: int = 120) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


VISION = ToolEntry(
    definition=ToolDefinition(
        name="vision",
        description=(
            "Analyse une image locale avec Ollama en local. "
            "Utilise le modèle MARIUS_VISION_MODEL ou `gemma4` par défaut."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin absolu ou relatif de l'image à analyser.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Question ou consigne d'analyse visuelle.",
                },
                "model": {
                    "type": "string",
                    "description": "Modèle Ollama vision à utiliser (défaut : gemma4).",
                },
            },
            "required": ["path"],
        },
    ),
    handler=_vision,
)
