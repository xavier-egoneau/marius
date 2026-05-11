from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.context_builder import (
    ContextBuildInput,
    ContextBuilder,
    ContextSource,
    MissingContextSourceError,
)


class FakeReader:
    def __init__(self, values: dict[Path, str | None]) -> None:
        self.values = values

    def read_text(self, path: Path) -> str | None:
        return self.values.get(path)


def test_context_builder_assembles_markdown_sources_in_declared_order() -> None:
    soul = Path("/tmp/SOUL.md")
    user = Path("/tmp/USER.md")
    agents = Path("/repo/AGENTS.md")

    builder = ContextBuilder(
        reader=FakeReader(
            {
                soul: "âme",
                user: "préférences",
                agents: "conventions projet",
            }
        )
    )

    bundle = builder.build(
        ContextBuildInput(
            preamble="Tu es Marius.",
            sources=[
                ContextSource(key="soul", title="SOUL", path=soul, required=False),
                ContextSource(key="user", title="USER", path=user, required=False),
                ContextSource(key="agents", title="AGENTS", path=agents),
            ],
        )
    )

    assert bundle.markdown == (
        "Tu es Marius.\n\n"
        "## SOUL\nâme\n\n"
        "## USER\npréférences\n\n"
        "## AGENTS\nconventions projet"
    )


def test_context_builder_raises_on_missing_required_source() -> None:
    source = ContextSource(key="agents", title="AGENTS", path=Path("/repo/AGENTS.md"))
    builder = ContextBuilder(reader=FakeReader({}))

    with pytest.raises(MissingContextSourceError) as error:
        builder.build(ContextBuildInput(sources=[source]))

    assert error.value.source == source


def test_context_builder_raises_on_empty_required_source() -> None:
    source = ContextSource(key="agents", title="AGENTS", path=Path("/repo/AGENTS.md"))
    builder = ContextBuilder(reader=FakeReader({source.path: " \n\t "}))

    with pytest.raises(MissingContextSourceError) as error:
        builder.build(ContextBuildInput(sources=[source]))

    assert error.value.source == source


def test_context_builder_skips_missing_optional_source_and_tracks_it() -> None:
    soul = ContextSource(
        key="soul",
        title="SOUL",
        path=Path("/tmp/SOUL.md"),
        required=False,
    )
    agents = ContextSource(key="agents", title="AGENTS", path=Path("/repo/AGENTS.md"))
    builder = ContextBuilder(reader=FakeReader({agents.path: "conventions"}))

    bundle = builder.build(ContextBuildInput(sources=[soul, agents]))

    assert bundle.missing_optional_sources == [soul]
    assert bundle.markdown == "## AGENTS\nconventions"


def test_context_builder_omits_empty_markdown_sections() -> None:
    user = ContextSource(key="user", title="USER", path=Path("/tmp/USER.md"), required=False)
    agents = ContextSource(key="agents", title="AGENTS", path=Path("/repo/AGENTS.md"))
    builder = ContextBuilder(
        reader=FakeReader(
            {
                user.path: "  \n\t  ",
                agents.path: "règles",
            }
        )
    )

    bundle = builder.build(ContextBuildInput(sources=[user, agents]))

    assert "## USER" not in bundle.markdown
    assert bundle.markdown == "## AGENTS\nrègles"


def test_context_builder_returns_loaded_source_metadata() -> None:
    soul = ContextSource(key="soul", title="SOUL", path=Path("/tmp/SOUL.md"), required=False)
    agents = ContextSource(key="agents", title="AGENTS", path=Path("/repo/AGENTS.md"))
    builder = ContextBuilder(
        reader=FakeReader(
            {
                soul.path: "âme",
                agents.path: "conventions",
            }
        )
    )

    bundle = builder.build(ContextBuildInput(sources=[soul, agents], preamble="Préambule"))

    assert bundle.loaded_sources == [soul, agents]
    assert bundle.metadata["source_count"] == 2
    assert bundle.metadata["loaded_source_keys"] == ["soul", "agents"]
    assert bundle.metadata["has_preamble"] is True
