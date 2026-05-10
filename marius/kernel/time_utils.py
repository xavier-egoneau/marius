"""Utilitaires datetime partagés dans le kernel.

Règle : tout timestamp stocké est en ISO 8601 UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_stored_dt(iso: str) -> datetime:
    """Parse un timestamp ISO 8601 stocké. Suppose UTC si tzinfo absent."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
