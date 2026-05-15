from __future__ import annotations

from marius.dreaming.context import DreamingContext
from marius.dreaming.prompt import build_dreaming_prompt


def test_dreaming_prompt_requires_json_operations() -> None:
    prompt = build_dreaming_prompt(DreamingContext())

    assert "consolidation mémorielle" in prompt
    assert "operations" in prompt
    assert "Réponds UNIQUEMENT avec un objet JSON valide" in prompt
