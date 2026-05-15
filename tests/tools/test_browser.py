from __future__ import annotations

from marius.tools.browser import make_browser_tools


def _tools(tmp_path):
    return make_browser_tools(tmp_path)


def test_browser_open_rejects_non_http_url(tmp_path):
    result = _tools(tmp_path)["browser_open"].handler({"url": "file:///etc/passwd"})

    assert result.ok is False
    assert result.error == "unsupported_url_scheme"


def test_browser_extract_requires_open_page(tmp_path):
    result = _tools(tmp_path)["browser_extract"].handler({})

    assert result.ok is False
    assert result.error == "no_page"


def test_browser_open_reports_missing_playwright(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = _tools(tmp_path)["browser_open"].handler({"url": "https://example.com"})

    assert result.ok is False
    assert result.error == "playwright_missing"
    assert "python -m playwright install chromium" in result.summary
