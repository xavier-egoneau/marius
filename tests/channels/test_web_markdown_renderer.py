from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


UI_HTML = Path(__file__).resolve().parents[2] / "marius" / "channels" / "web" / "ui.html"


def _render_with_node(markdown: str) -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the browser markdown renderer")
    html = UI_HTML.read_text(encoding="utf-8")
    start = html.index("function renderMarkdown")
    end = html.index("// ── send")
    script = (
        html[start:end]
        + "\nconst out = renderMarkdown(process.argv[1]);"
        + "\nprocess.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "-e", script, markdown],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_web_markdown_renderer_keeps_diff_fences_readable() -> None:
    rendered = _render_with_node("**Diff — `README.md`**\n```diff\n-old\n+new\n```")

    assert "<strong>Diff" in rendered
    assert "<code>README.md</code>" in rendered
    assert '<pre><code class="lang-diff">-old\n+new</code></pre>' in rendered


def test_web_markdown_renderer_escapes_quotes_and_code_content() -> None:
    rendered = _render_with_node('Texte "cité" <tag>\n\n`**pas gras**`')

    assert "&quot;cité&quot;" in rendered
    assert "&lt;tag&gt;" in rendered
    assert "<code>**pas gras**</code>" in rendered
