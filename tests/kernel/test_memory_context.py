from __future__ import annotations

from dataclasses import dataclass

from marius.kernel.memory_context import MemoryBlock, format_memory_block


@dataclass
class _Entry:
    id: int
    content: str
    category: str = "general"
    tags: str = ""


def test_format_returns_none_for_empty_list() -> None:
    assert format_memory_block([]) is None


def test_format_returns_memory_block() -> None:
    entries = [_Entry(id=1, content="J'aime le café")]
    result = format_memory_block(entries)
    assert isinstance(result, MemoryBlock)


def test_format_includes_content() -> None:
    entries = [_Entry(id=1, content="Python est mon langage préféré")]
    result = format_memory_block(entries)
    assert result is not None
    assert "Python est mon langage préféré" in result.text


def test_format_wraps_in_memory_tags() -> None:
    entries = [_Entry(id=1, content="quelque chose")]
    result = format_memory_block(entries)
    assert result is not None
    assert result.text.startswith("<memory>")
    assert result.text.endswith("</memory>")


def test_format_omits_empty_tags() -> None:
    entries = [_Entry(id=1, content="sans tags", tags="")]
    result = format_memory_block(entries)
    assert result is not None
    assert "[" not in result.text


def test_format_includes_tags_when_present() -> None:
    entries = [_Entry(id=1, content="avec tags", tags="tech,python")]
    result = format_memory_block(entries)
    assert result is not None
    assert "[tech,python]" in result.text


def test_format_count_matches_entries() -> None:
    entries = [_Entry(id=i, content=f"souvenir {i}") for i in range(3)]
    result = format_memory_block(entries)
    assert result is not None
    assert result.count == 3


def test_format_multiple_entries_each_on_own_line() -> None:
    entries = [
        _Entry(id=1, content="premier"),
        _Entry(id=2, content="deuxième"),
    ]
    result = format_memory_block(entries)
    assert result is not None
    assert "- premier" in result.text
    assert "- deuxième" in result.text
