"""Moteur dreaming/daily — appel LLM direct + orchestration du cycle."""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from marius.adapters.http_provider import make_adapter
from marius.kernel.contracts import ContextUsage, Message, Role
from marius.kernel.provider import ProviderChunk, ProviderError, ProviderRequest
from marius.provider_config.contracts import ProviderEntry
from marius.storage.memory_store import MemoryStore
from marius.storage.session_corpus import archive_session_file, list_unprocessed

from .context import DreamingContext, build_dreaming_context
from .operations import DreamingResult, apply_operations, parse_response
from .prompt import build_daily_prompt, build_dreaming_prompt
from .report import DreamReport, load_last_dream_report, save_dream_report


@dataclass(frozen=True)
class LLMCallResult:
    text: str
    usage: ContextUsage
    model: str = ""


def run_dreaming(
    memory_store: MemoryStore,
    entry: ProviderEntry,
    *,
    active_skills: list[str] | None = None,
    project_root: Path | None = None,
    sessions_dir: Path | None = None,
    dreams_dir: Path | None = None,
    skills_dir: Path | None = None,
    watch_dir: Path | None = None,
    archive_sessions: bool = True,
) -> DreamingResult:
    """Cycle complet de dreaming.

    1. Collecte le contexte (mémoires, sessions, contrats, docs projet)
    2. Appel LLM unique
    3. Parse et applique les opérations JSON
    4. Persiste le rapport de dream en JSON
    5. Archive les sessions traitées
    """
    ctx = build_dreaming_context(
        memory_store=memory_store,
        active_skills=active_skills,
        project_root=project_root,
        sessions_dir=sessions_dir,
        skills_dir=skills_dir,
        watch_dir=watch_dir,
    )

    if ctx.is_empty:
        return DreamingResult(summary="Rien à consolider — mémoire et contrats vides.")

    system_prompt = build_dreaming_prompt(ctx)
    try:
        response = _call_llm(entry, system_prompt, "Consolide la mémoire.")
    except ProviderError as exc:
        return DreamingResult(
            errors=1,
            summary=f"Dreaming impossible : erreur provider — {exc}",
        )

    ops, llm_summary = parse_response(response)
    project_path = str(project_root.resolve()) if project_root else None
    result = apply_operations(ops, memory_store, project_path=project_path)
    result.summary = llm_summary or str(result)

    # Persiste le rapport
    report = DreamReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        added=result.added,
        updated=result.updated,
        removed=result.removed,
        errors=result.errors,
        summary=result.summary,
        memories_count=len(ctx.memories),
        sessions_count=len(ctx.session_summaries),
        skills=[name for name, _ in ctx.dream_contracts],
    )
    save_dream_report(report, dreams_dir)

    if archive_sessions:
        for path in list_unprocessed(sessions_dir):
            try:
                archive_session_file(path)
            except OSError:
                pass

    return result


def run_daily(
    memory_store: MemoryStore,
    entry: ProviderEntry,
    *,
    active_skills: list[str] | None = None,
    project_root: Path | None = None,
    dreams_dir: Path | None = None,
    skills_dir: Path | None = None,
    watch_dir: Path | None = None,
    model: str | None = None,
) -> str:
    """Génère le briefing quotidien en Markdown.

    1. Collecte mémoires + contrats daily + dernier rapport de dream
    2. Appel LLM unique
    3. Retourne le Markdown brut
    """
    ctx = build_dreaming_context(
        memory_store=memory_store,
        active_skills=active_skills,
        project_root=project_root,
        skills_dir=skills_dir,
        watch_dir=watch_dir,
    )

    if not ctx.memories and not ctx.daily_contracts:
        return (
            "# Briefing\n\n"
            "Aucune mémoire ni contrat daily actif.\n"
            "Lancez `/dream` d'abord pour consolider la mémoire, "
            "ou ajoutez un skill avec un `DAILY.md`."
        )

    last_report = load_last_dream_report(dreams_dir)
    system_prompt = build_daily_prompt(ctx, last_dream_report=last_report)
    daily_entry = _with_model(entry, model) if model else entry
    try:
        result = _call_llm_with_usage(daily_entry, system_prompt, "Génère mon briefing du jour.")
        return _with_daily_usage_footer(result.text, result.usage, result.model or daily_entry.model)
    except ProviderError as exc:
        return f"# Briefing\n\nErreur provider : {exc}"


# ── helpers ───────────────────────────────────────────────────────────────────


def _call_llm(entry: ProviderEntry, system_prompt: str, user_message: str) -> str:
    """Appel LLM direct (streaming collecté). Ne passe pas par l'orchestrateur."""
    return _call_llm_with_usage(entry, system_prompt, user_message).text


def _with_model(entry: ProviderEntry, model: str | None) -> ProviderEntry:
    if not model:
        return entry
    if is_dataclass(entry):
        return replace(entry, model=model)
    data = dict(getattr(entry, "__dict__", {}))
    data["model"] = model
    return type(entry)(**data)


def _call_llm_with_usage(entry: ProviderEntry, system_prompt: str, user_message: str) -> LLMCallResult:
    """Appel LLM direct avec récupération best-effort de l'usage tokens."""
    adapter = make_adapter(entry)
    now = datetime.now(timezone.utc)
    messages = [
        Message(role=Role.SYSTEM, content=system_prompt, created_at=now),
        Message(role=Role.USER,   content=user_message,  created_at=now),
    ]
    request = ProviderRequest(messages=messages, tools=[])
    text = ""
    usage = ContextUsage()
    for chunk in adapter.stream(request):
        if chunk.type == "text_delta":
            text += chunk.delta
        elif chunk.type in {"usage", "done"}:
            usage = _chunk_usage(chunk, usage)
    return LLMCallResult(text=text, usage=usage, model=entry.model)


def _chunk_usage(chunk: ProviderChunk, current: ContextUsage) -> ContextUsage:
    raw = chunk.usage
    if raw is None:
        return current
    if isinstance(raw, ContextUsage):
        return raw
    if isinstance(raw, dict):
        return ContextUsage(
            estimated_input_tokens=int(raw.get("input_tokens") or current.estimated_input_tokens or 0),
            provider_input_tokens=raw.get("input_tokens", current.provider_input_tokens),
            provider_output_tokens=raw.get("output_tokens", current.provider_output_tokens),
            max_context_tokens=current.max_context_tokens,
        )
    return current


def _with_daily_usage_footer(markdown: str, usage: ContextUsage, model: str) -> str:
    input_tokens = usage.provider_input_tokens or usage.estimated_input_tokens
    output_tokens = usage.provider_output_tokens
    if not input_tokens and output_tokens is None and not model:
        return markdown
    parts: list[str] = []
    if input_tokens:
        parts.append(f"entrée {input_tokens:,}".replace(",", " "))
    if output_tokens is not None:
        parts.append(f"sortie {output_tokens:,}".replace(",", " "))
    if input_tokens and output_tokens is not None:
        parts.append(f"total {(input_tokens + output_tokens):,}".replace(",", " "))
    if model:
        parts.append(f"modèle `{model}`")
    if not parts:
        return markdown
    return markdown.rstrip() + "\n\n---\n_Tokens daily : " + " · ".join(parts) + "_"
