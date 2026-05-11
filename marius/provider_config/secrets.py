"""Provider secret resolution helpers.

Existing raw api_key values remain supported for backwards compatibility.
New agent-facing tools should store references (secret:, env:, file:) instead
of raw values.
"""

from __future__ import annotations

import os
from pathlib import Path

from marius.storage.secret_ref_store import SecretRefStore


def resolve_provider_secret(value: str, *, secret_ref_path: Path | None = None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith("secret:"):
        secret = SecretRefStore(path=secret_ref_path).get(text[7:].strip())
        if secret is None:
            return ""
        return resolve_provider_secret(secret.ref, secret_ref_path=secret_ref_path)
    if text.startswith("env:"):
        return os.environ.get(text[4:].strip(), "").strip()
    if text.startswith("file:"):
        path = Path(text[5:].strip()).expanduser()
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return text


def is_secret_reference(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith(("secret:", "env:", "file:"))


def public_secret_label(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if is_secret_reference(text):
        return text
    return "<legacy-raw-secret>"
