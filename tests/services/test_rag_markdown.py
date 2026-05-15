from __future__ import annotations

from marius.services.rag_markdown import parse_markdown_file


def test_parse_markdown_file_reads_frontmatter_and_inline_tags(tmp_path):
    path = tmp_path / "rules.md"
    path.write_text(
        """---
scope: org
audience: devs
tags: [security]
---

# Rules

[always] Never expose raw secrets.

## Tokens

[important] Store tokens by reference.
""",
        encoding="utf-8",
    )

    doc = parse_markdown_file(path)

    assert doc.title == "Rules"
    assert doc.metadata["scope"] == "org"
    assert doc.tags == ["security"]
    assert len(doc.chunks) == 2
    assert doc.chunks[0].tags == ["security", "always"]
    assert doc.chunks[0].importance == 100
    assert doc.chunks[1].tags == ["security", "important"]
    assert doc.chunks[1].importance == 80


def test_parse_markdown_file_detects_obsidian_tags_and_archive(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        """# Notes

Tags: #project/marius #archive

Old note.
""",
        encoding="utf-8",
    )

    doc = parse_markdown_file(path)

    assert doc.chunks[0].archived is True
    assert "project-marius" in doc.chunks[0].tags
    assert "archive" in doc.chunks[0].tags


def test_parse_markdown_file_cleans_inline_tags_from_titles(tmp_path):
    path = tmp_path / "courses.md"
    path.write_text("# Courses [important], [routine]\n\n- Cafe\n", encoding="utf-8")

    doc = parse_markdown_file(path)

    assert doc.title == "Courses"
    assert doc.chunks[0].title == "Courses"
