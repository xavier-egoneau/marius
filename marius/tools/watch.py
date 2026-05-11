"""Persistent watch tools.

Topics are stored explicitly and run on demand. Search results are observations
for the LLM; they do not replace the model's final answer.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolResult
from marius.kernel.provider import ProviderError, ProviderRequest
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.provider_config.contracts import ProviderEntry
from marius.storage.watch_store import WatchStore
from marius.tools.web import WEB_SEARCH

SearchHandler = Callable[[dict[str, Any]], ToolResult]
WatchSummarizer = Callable[[Any, list[dict[str, Any]], dict[str, Any]], str]


def make_watch_tools(
    store: WatchStore | None = None,
    *,
    root: Path | None = None,
    search_handler: SearchHandler | None = None,
    summarizer: WatchSummarizer | None = None,
) -> dict[str, ToolEntry]:
    watch_store = store if store is not None else WatchStore(root)
    search = search_handler or WEB_SEARCH.handler

    def watch_add(arguments: dict[str, Any]) -> ToolResult:
        title = _text(arguments.get("title"))
        query = _text(arguments.get("query"))
        if not title:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `title` missing.", error="missing_arg:title")
        if not query:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `query` missing.", error="missing_arg:query")
        try:
            topic = watch_store.add(
                title=title,
                query=query,
                cadence=_text(arguments.get("cadence")) or "manual",
                tags=_string_list(arguments.get("tags")),
                settings=_settings_from_args(arguments),
                topic_id=_text(arguments.get("id")) or None,
            )
        except ValueError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc), error="invalid_topic_id")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Watch topic saved: {topic.id} — {topic.title}",
            data={"topic": asdict(topic)},
        )

    def watch_list(arguments: dict[str, Any]) -> ToolResult:
        include_disabled = bool(arguments.get("include_disabled", True))
        topics = watch_store.list_topics(include_disabled=include_disabled)
        lines = [f"Watch topics: {len(topics)} topic(s)."]
        for topic in topics:
            status = "enabled" if topic.enabled else "disabled"
            last = f", last run {topic.last_run_at[:16]}" if topic.last_run_at else ""
            lines.append(f"- {topic.id}: {topic.title} ({status}, {topic.cadence}{last})")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={"topics": [asdict(topic) for topic in topics]},
        )

    def watch_remove(arguments: dict[str, Any]) -> ToolResult:
        topic_id = _text(arguments.get("id"))
        if not topic_id:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `id` missing.", error="missing_arg:id")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Removal requires `confirm: true`.", error="confirmation_required")
        if not watch_store.remove(topic_id):
            return ToolResult(tool_call_id="", ok=False, summary=f"Watch topic not found: {topic_id}", error="topic_not_found")
        return ToolResult(tool_call_id="", ok=True, summary=f"Watch topic removed: {topic_id}", data={"id": topic_id})

    def watch_run(arguments: dict[str, Any]) -> ToolResult:
        topic_id = _text(arguments.get("id"))
        max_results = _bounded_int(arguments.get("max_results"), default=5, minimum=1, maximum=20)
        dedupe = _optional_bool(arguments.get("dedupe"), True)
        topics = [watch_store.get(topic_id)] if topic_id else watch_store.list_topics(include_disabled=False)
        topics = [topic for topic in topics if topic is not None and topic.enabled]
        if not topics:
            return ToolResult(tool_call_id="", ok=False, summary="No enabled watch topic to run.", error="no_topic")

        reports = []
        lines = [f"Watch run: {len(topics)} topic(s)."]
        for topic in topics:
            search_result = search({"query": topic.query, "max_results": max_results})
            if not search_result.ok:
                lines.append(f"- {topic.id}: search failed — {search_result.summary}")
                reports.append({"topic": asdict(topic), "ok": False, "error": search_result.error, "summary": search_result.summary})
                continue
            raw_results = _search_results(search_result)
            results = _score_results(raw_results, topic, watch_store.last_seen_urls(topic.id))
            duplicate_count = 0
            if dedupe:
                results, duplicate_count = watch_store.dedupe_results(topic.id, results)
            metadata = _result_metrics(results)
            metadata["duplicate_count"] = duplicate_count
            metadata["dedupe"] = dedupe
            llm_summary, summary_status = _maybe_summarize(topic, results, metadata, arguments, summarizer)
            metadata["summary_status"] = summary_status
            if llm_summary:
                metadata["llm_summary"] = llm_summary
            summary = _report_summary(topic, len(raw_results), len(results), duplicate_count, llm_summary)
            report = watch_store.save_report(
                topic,
                results,
                summary=summary,
                dedupe=False,
                metadata=metadata,
            )
            novelty = report.metadata.get("max_novelty_score", 0.0)
            lines.append(f"- {topic.id}: {len(results)} result(s) saved, novelty max {novelty}")
            if llm_summary:
                lines.append(f"  summary: {_collapse_text(llm_summary, limit=900)}")
            reports.append({"topic": asdict(topic), "ok": True, "report": asdict(report)})

        markdown = _run_markdown(reports)
        return ToolResult(
            tool_call_id="",
            ok=any(item.get("ok") for item in reports),
            summary="\n".join(lines),
            data={"reports": reports},
            artifacts=[Artifact(type=ArtifactType.REPORT, path="watch-run.md", data={"content": markdown})],
        )

    return {
        "watch_add": ToolEntry(
            definition=ToolDefinition(
                name="watch_add",
                description="Create or update a persistent watch topic with an explicit web search query.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Optional stable topic id."},
                        "title": {"type": "string"},
                        "query": {"type": "string"},
                        "cadence": {"type": "string", "description": "Human cadence label, default manual."},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "summary_enabled": {"type": "boolean", "description": "Whether watch_run should ask the LLM for a topic summary when available. Default true."},
                        "notify": {
                            "type": "string",
                            "enum": ["off", "tagged", "new", "always"],
                            "description": "Notification mode. tagged keeps the legacy notify/telegram tag behavior.",
                        },
                        "notify_min_score": {
                            "type": "number",
                            "description": "Minimum max novelty score required for notifications. Default 0.",
                        },
                        "settings": {
                            "type": "object",
                            "description": "Optional advanced settings. Known keys: summary_enabled, notify, notify_min_score.",
                        },
                    },
                    "required": ["title", "query"],
                },
            ),
            handler=watch_add,
        ),
        "watch_list": ToolEntry(
            definition=ToolDefinition(
                name="watch_list",
                description="List persistent watch topics.",
                parameters={
                    "type": "object",
                    "properties": {
                        "include_disabled": {"type": "boolean"},
                    },
                    "required": [],
                },
            ),
            handler=watch_list,
        ),
        "watch_remove": ToolEntry(
            definition=ToolDefinition(
                name="watch_remove",
                description="Remove a watch topic after explicit confirmation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confirm": {"type": "boolean"},
                    },
                    "required": ["id", "confirm"],
                },
            ),
            handler=watch_remove,
        ),
        "watch_run": ToolEntry(
            definition=ToolDefinition(
                name="watch_run",
                description="Run one or all enabled watch topics via web search and persist a report.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Optional topic id. If omitted, runs all enabled topics."},
                        "max_results": {"type": "integer", "description": "Results per topic, default 5, max 20."},
                        "summarize": {"type": "boolean", "description": "Override topic summary setting for this run."},
                        "dedupe": {"type": "boolean", "description": "Keep true by default. Set false only for controlled backfill or audit runs."},
                    },
                    "required": [],
                },
            ),
            handler=watch_run,
        ),
    }


_DEFAULT_TOOLS = make_watch_tools()
WATCH_ADD = _DEFAULT_TOOLS["watch_add"]
WATCH_LIST = _DEFAULT_TOOLS["watch_list"]
WATCH_REMOVE = _DEFAULT_TOOLS["watch_remove"]
WATCH_RUN = _DEFAULT_TOOLS["watch_run"]


def make_provider_watch_summarizer(entry: ProviderEntry) -> WatchSummarizer:
    """Build an optional LLM summarizer for watch reports.

    The watch tool remains usable without this helper; callers inject it when a
    provider is available. The returned text is stored as an observation and the
    main assistant still owns the final answer.
    """
    from marius.adapters.http_provider import make_adapter

    def summarize(topic: Any, results: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        adapter = make_adapter(entry)
        payload = _summary_payload(topic, results, metadata)
        response = adapter.generate(
            ProviderRequest(
                messages=[
                    Message(
                        role=Role.SYSTEM,
                        content=(
                            "Tu résumes une veille pour Marius. Réponds en français, "
                            "en Markdown concis, sans inventer d'information absente des résultats."
                        ),
                        created_at=datetime.now(timezone.utc),
                    ),
                    Message(
                        role=Role.USER,
                        content=payload,
                        created_at=datetime.now(timezone.utc),
                    ),
                ],
                metadata={"tool": "watch_run", "purpose": "topic_summary"},
            )
        )
        return response.message.content.strip()

    return summarize


def should_notify_topic(topic: Any, report: dict[str, Any]) -> bool:
    settings = _topic_settings(topic)
    mode = str(settings.get("notify") or "tagged").strip().lower()
    metadata = _dict(report.get("metadata"))
    max_score = _float(metadata.get("max_novelty_score"), 0.0)
    min_score = _float(settings.get("notify_min_score"), 0.0)
    if max_score < min_score:
        return False
    if mode == "off":
        return False
    if mode == "always":
        return True
    if mode == "new":
        return int(metadata.get("new_count") or 0) > 0
    tags = set(getattr(topic, "tags", []) or [])
    return bool(tags & {"notify", "telegram"})


def _search_results(result: ToolResult) -> list[dict[str, Any]]:
    raw = result.data.get("results", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _run_markdown(reports: list[dict[str, Any]]) -> str:
    lines = ["# Watch Run", ""]
    for item in reports:
        topic = item.get("topic") or {}
        lines.append(f"## {topic.get('title', topic.get('id', 'topic'))}")
        if not item.get("ok"):
            lines.append("")
            lines.append(f"Search failed: {item.get('summary', 'unknown error')}")
            lines.append("")
            continue
        report = item.get("report") or {}
        lines.append("")
        lines.append(f"Query: `{report.get('query', '')}`")
        summary = _text(_dict(report.get("metadata")).get("llm_summary"))
        if summary:
            lines.append("")
            lines.append("### Summary")
            lines.append("")
            lines.append(summary)
        report_summary = _text(report.get("summary"))
        if report_summary:
            lines.append("")
            lines.append(f"Run: {report_summary}")
        lines.append("")
        for result in report.get("results", []):
            title = result.get("title") or result.get("url") or "result"
            url = result.get("url") or ""
            content = result.get("content") or ""
            score = _float(result.get("novelty_score"), 0.0)
            prefix = f"`{score:.2f}` "
            lines.append(f"- {prefix}[{title}]({url}) — {content}" if url else f"- {prefix}{title} — {content}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _score_results(results: list[dict[str, Any]], topic: Any, seen_urls: set[str]) -> list[dict[str, Any]]:
    terms = _query_terms(str(getattr(topic, "query", "")))
    seen_domains = {_domain(url) for url in seen_urls if _domain(url)}
    run_seen = set(seen_urls)
    scored: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        url = _text(item.get("url"))
        haystack = " ".join(
            _text(item.get(key)).lower()
            for key in ("title", "content", "snippet", "description")
        )
        reasons: list[str] = []
        score = 0.0
        is_new = not url or url not in run_seen
        if is_new:
            score += 0.55
            reasons.append("new_url" if url else "no_url")
        else:
            score += 0.05
            reasons.append("seen_url")
        domain = _domain(url)
        if domain and domain not in seen_domains:
            score += 0.15
            reasons.append("new_domain")
        if terms:
            overlap = sum(1 for term in terms if term in haystack)
            if overlap:
                score += min(0.25, overlap / len(terms) * 0.25)
                reasons.append("query_match")
        if _text(item.get("published_at") or item.get("published") or item.get("date")):
            score += 0.05
            reasons.append("dated")
        item["is_new"] = is_new
        item["novelty_score"] = round(min(score, 1.0), 3)
        item["novelty_reasons"] = reasons
        scored.append(item)
        if url:
            run_seen.add(url)
            if domain:
                seen_domains.add(domain)
    return scored


def _maybe_summarize(
    topic: Any,
    results: list[dict[str, Any]],
    metadata: dict[str, Any],
    arguments: dict[str, Any],
    summarizer: WatchSummarizer | None,
) -> tuple[str, str]:
    if not _summary_enabled(topic, arguments.get("summarize")):
        return "", "disabled"
    if not results:
        return "", "empty"
    if summarizer is None:
        return "", "unavailable"
    try:
        summary = summarizer(topic, results, metadata)
    except ProviderError as exc:
        return "", f"provider_error:{exc.provider_name or 'unknown'}"
    except Exception:
        return "", "failed"
    return summary.strip(), "ok" if summary.strip() else "empty_response"


def _summary_enabled(topic: Any, override: object) -> bool:
    if override is not None:
        return _optional_bool(override, True)
    settings = _topic_settings(topic)
    return _optional_bool(settings.get("summary_enabled"), True)


def _report_summary(topic: Any, raw_count: int, saved_count: int, duplicate_count: int, llm_summary: str) -> str:
    parts = [f"{saved_count}/{raw_count} result(s) saved for {getattr(topic, 'query', '')!r}"]
    if duplicate_count:
        parts.append(f"{duplicate_count} duplicate result(s) skipped")
    if llm_summary:
        parts.append(f"LLM summary: {_collapse_text(llm_summary, limit=500)}")
    return "; ".join(parts)


def _result_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [_float(item.get("novelty_score"), 0.0) for item in results]
    new_count = sum(1 for item in results if bool(item.get("is_new", False)))
    return {
        "result_count": len(results),
        "new_count": new_count,
        "max_novelty_score": max(scores) if scores else 0.0,
        "average_novelty_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
    }


def _settings_from_args(arguments: dict[str, Any]) -> dict[str, Any] | None:
    raw = arguments.get("settings")
    settings = dict(raw) if isinstance(raw, dict) else {}
    if "summary_enabled" in arguments:
        settings["summary_enabled"] = _optional_bool(arguments.get("summary_enabled"), True)
    if "notify" in arguments:
        notify = _text(arguments.get("notify")).lower()
        if notify in {"off", "tagged", "new", "always"}:
            settings["notify"] = notify
    if "notify_min_score" in arguments:
        settings["notify_min_score"] = _float(arguments.get("notify_min_score"), 0.0)
    return settings if settings else None


def _topic_settings(topic: Any) -> dict[str, Any]:
    return _dict(getattr(topic, "settings", {}))


def _summary_payload(topic: Any, results: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    lines = [
        f"Topic: {getattr(topic, 'title', '')}",
        f"Query: {getattr(topic, 'query', '')}",
        f"Metrics: {metadata}",
        "",
        "Résultats:",
    ]
    for result in results[:10]:
        lines.append(
            "- "
            f"title={_text(result.get('title'))}; "
            f"url={_text(result.get('url'))}; "
            f"score={_float(result.get('novelty_score'), 0.0):.2f}; "
            f"content={_text(result.get('content') or result.get('snippet') or result.get('description'))}"
        )
    return "\n".join(lines)


def _query_terms(query: str) -> list[str]:
    stop = {"avec", "dans", "from", "pour", "the", "and", "les", "des", "une", "sur", "news"}
    terms: list[str] = []
    for raw in query.lower().replace('"', " ").replace("'", " ").split():
        term = "".join(char for char in raw if char.isalnum() or char in "-_").strip("-_")
        if len(term) >= 3 and term not in stop and term not in terms:
            terms.append(term)
    return terms[:12]


def _domain(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _collapse_text(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "oui", "o", "on"}
    return bool(value)
