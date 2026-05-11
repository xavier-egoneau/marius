from __future__ import annotations

from marius.channels.telegram.api import _md_to_html, _split_message


def test_telegram_markdown_keeps_formatting_outside_inline_code() -> None:
    html, mode = _md_to_html("**gras** et `**pas gras**`")

    assert mode == "HTML"
    assert "<b>gras</b>" in html
    assert "<code>**pas gras**</code>" in html


def test_telegram_markdown_escapes_code_blocks() -> None:
    html, _mode = _md_to_html("```diff\n-a <tag>\n+new & old\n```")

    assert html == "<pre>-a &lt;tag&gt;\n+new &amp; old\n</pre>"


def test_telegram_split_preserves_markdown_fences_for_long_diffs() -> None:
    text = "**Diff**\n```diff\n" + "".join(f"+line {i}\n" for i in range(30)) + "```\nFin"

    chunks = _split_message(text, limit=120)

    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert all(chunk.count("```") % 2 == 0 for chunk in chunks)
    assert all("```diff" not in chunk or "```" in chunk for chunk in chunks)
