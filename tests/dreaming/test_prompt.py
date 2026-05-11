from __future__ import annotations

from marius.dreaming.context import DreamingContext
from marius.dreaming.prompt import build_daily_prompt


def test_daily_prompt_requires_structured_useful_briefing() -> None:
    prompt = build_daily_prompt(DreamingContext())

    assert "agenda" in prompt.lower()
    assert "priorités/listes" in prompt
    assert "veille utile" in prompt
    assert "croisements/déductions" in prompt
    assert "n'a pas été vérifiée" in prompt
