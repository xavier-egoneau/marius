from __future__ import annotations

from marius.kernel.contracts import ToolResult
from marius.kernel.contracts import ArtifactType
from marius.storage.watch_store import WatchStore
from marius.tools.watch import make_watch_tools


def _search(args):
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary="ok",
        data={
            "results": [
                {
                    "title": f"Result for {args['query']}",
                    "url": "https://example.com/news/marius-update-2026",
                    "content": "Short release summary",
                }
            ]
        },
    )


def test_watch_add_list_remove(tmp_path):
    tools = make_watch_tools(root=tmp_path, search_handler=_search)

    added = tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"})
    listed = tools["watch_list"].handler({})
    no_confirm = tools["watch_remove"].handler({"id": added.data["topic"]["id"]})
    removed = tools["watch_remove"].handler({"id": added.data["topic"]["id"], "confirm": True})

    assert added.ok is True
    assert listed.data["topics"][0]["title"] == "Marius"
    assert no_confirm.error == "confirmation_required"
    assert removed.ok is True


def test_watch_add_warns_before_ninth_scheduled_topic(tmp_path):
    tools = make_watch_tools(root=tmp_path, search_handler=_search)
    for index in range(8):
        result = tools["watch_add"].handler(
            {
                "title": f"Topic {index}",
                "query": f"topic {index} news",
                "cadence": "daily",
            }
        )
        assert result.ok is True

    warning = tools["watch_add"].handler(
        {
            "title": "Topic 9",
            "query": "topic 9 news",
            "cadence": "daily",
        }
    )
    confirmed = tools["watch_add"].handler(
        {
            "title": "Topic 9",
            "query": "topic 9 news",
            "cadence": "daily",
            "confirm_over_limit": True,
        }
    )

    assert warning.ok is False
    assert warning.error == "watch_topic_limit_warning"
    assert warning.data["existing_count"] == 8
    assert warning.data["limit"] == 8
    assert "confirm_over_limit" in warning.summary
    assert confirmed.ok is True
    assert len(tools["watch_list"].handler({}).data["topics"]) == 9


def test_watch_add_manual_topic_ignores_daily_soft_limit(tmp_path):
    tools = make_watch_tools(root=tmp_path, search_handler=_search)
    for index in range(8):
        tools["watch_add"].handler(
            {
                "title": f"Topic {index}",
                "query": f"topic {index} news",
                "cadence": "daily",
            }
        )

    result = tools["watch_add"].handler(
        {
            "title": "Manual audit",
            "query": "manual audit",
            "cadence": "manual",
        }
    )

    assert result.ok is True


def test_watch_run_persists_report(tmp_path):
    store = WatchStore(tmp_path)
    tools = make_watch_tools(store=store, search_handler=_search)
    topic = tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"}).data["topic"]

    result = tools["watch_run"].handler({"id": topic["id"]})

    reports = store.list_reports()
    assert result.ok is True
    assert reports
    assert reports[0].query == "Marius updates"
    assert reports[0].metadata["new_count"] == 1
    assert reports[0].results[0]["novelty_score"] > 0
    assert result.artifacts[0].type == ArtifactType.REPORT
    assert result.artifacts[0].data["display"] is False


def test_watch_run_passes_bounded_search_controls(tmp_path):
    calls = []

    def search(args):
        calls.append(args)
        return _search(args)

    tools = make_watch_tools(root=tmp_path, search_handler=search)
    topic = tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"}).data["topic"]

    result = tools["watch_run"].handler(
        {
            "id": topic["id"],
            "max_results": 3,
            "timeout_seconds": 4,
            "retry_attempts": 1,
            "summarize": False,
        }
    )

    assert result.ok is True
    assert calls[0]["max_results"] == 3
    assert calls[0]["timeout_seconds"] == 4
    assert calls[0]["retry_attempts"] == 1


def test_watch_run_skips_portal_pages_when_possible(tmp_path):
    def search(args):
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="ok",
            data={
                "results": [
                    {
                        "title": "GitHub Trending",
                        "url": "https://github.com/trending",
                        "content": "Trending repositories on GitHub.",
                    },
                    {
                        "title": "owner/project",
                        "url": "https://github.com/owner/project",
                        "content": "Open source release with new features.",
                    },
                ]
            },
        )

    store = WatchStore(tmp_path)
    tools = make_watch_tools(store=store, search_handler=search)
    topic = tools["watch_add"].handler({"title": "Repos", "query": "GitHub trending repositories"}).data["topic"]

    result = tools["watch_run"].handler({"id": topic["id"], "summarize": False})
    report = store.list_reports()[0]

    assert result.ok is True
    assert report.metadata["skipped_portal_count"] == 1
    assert len(report.results) == 1
    assert report.results[0]["url"] == "https://github.com/owner/project"
    assert report.results[0]["watch_result_type"] == "specific"
    assert "portal/index" in report.summary


def test_watch_run_can_keep_portal_pages_for_audit(tmp_path):
    def search(args):
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="ok",
            data={
                "results": [
                    {
                        "title": "Le Monde IA",
                        "url": "https://www.lemonde.fr/intelligence-artificielle/",
                        "content": "Actualités intelligence artificielle.",
                    }
                ]
            },
        )

    store = WatchStore(tmp_path)
    tools = make_watch_tools(store=store, search_handler=search)
    topic = tools["watch_add"].handler({"title": "IA", "query": "IA actualité"}).data["topic"]

    tools["watch_run"].handler({"id": topic["id"], "include_portals": True, "summarize": False})
    report = store.list_reports()[0]

    assert report.metadata["skipped_portal_count"] == 0
    assert len(report.results) == 1
    assert report.results[0]["watch_result_type"] == "portal"


def test_watch_run_skips_duplicate_urls(tmp_path):
    store = WatchStore(tmp_path)
    tools = make_watch_tools(store=store, search_handler=_search)
    topic = tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"}).data["topic"]

    first = tools["watch_run"].handler({"id": topic["id"]})
    second = tools["watch_run"].handler({"id": topic["id"]})

    reports = store.list_reports()
    assert first.ok is True
    assert second.ok is True
    assert len(reports[0].results) == 0
    assert "duplicate" in reports[0].summary


def test_watch_run_reports_search_failure(tmp_path):
    def failing_search(args):
        return ToolResult(tool_call_id="", ok=False, summary="search down", error="down")

    tools = make_watch_tools(root=tmp_path, search_handler=failing_search)
    tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"})

    result = tools["watch_run"].handler({})

    assert result.ok is False
    assert "search failed" in result.summary


def test_watch_run_attaches_llm_summary_when_injected(tmp_path):
    store = WatchStore(tmp_path)

    def summarize(topic, results, metadata):
        assert topic.title == "Marius"
        assert results[0]["is_new"] is True
        assert metadata["new_count"] == 1
        return "Résumé court."

    tools = make_watch_tools(store=store, search_handler=_search, summarizer=summarize)
    topic = tools["watch_add"].handler(
        {
            "title": "Marius",
            "query": "Marius updates",
            "notify": "new",
            "notify_min_score": 0.5,
        }
    ).data["topic"]

    result = tools["watch_run"].handler({"id": topic["id"]})
    report = store.list_reports()[0]
    markdown = result.artifacts[0].data["content"]

    assert result.ok is True
    assert report.metadata["summary_status"] == "ok"
    assert report.metadata["llm_summary"] == "Résumé court."
    assert "Résumé court." in markdown
    assert store.get(topic["id"]).settings["notify"] == "new"


def test_watch_run_can_keep_seen_results_for_backfill(tmp_path):
    store = WatchStore(tmp_path)
    tools = make_watch_tools(store=store, search_handler=_search)
    topic = tools["watch_add"].handler({"title": "Marius", "query": "Marius updates"}).data["topic"]

    tools["watch_run"].handler({"id": topic["id"]})
    result = tools["watch_run"].handler({"id": topic["id"], "dedupe": False, "summarize": False})

    report = store.list_reports()[0]
    assert result.ok is True
    assert len(report.results) == 1
    assert report.results[0]["is_new"] is False
    assert report.metadata["dedupe"] is False
