from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

from marius.config.doctor import Section
from marius.gateway.server import GatewayServer
from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolCall, ToolResult
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig
from marius.kernel.runtime import RuntimeOrchestrator, TurnOutput
from marius.kernel.session import SessionRuntime
from marius.kernel.skills import SkillCommand
from marius.kernel.tool_router import ToolRouter
from marius.storage.memory_store import MemoryStore
from marius.tools.watch import make_watch_tools


class _SilentOrchestrator:
    def __init__(self, output: TurnOutput, *, stream_text: str = "") -> None:
        self.output = output
        self.stream_text = stream_text

    def run_turn(self, *_args, **kwargs) -> TurnOutput:
        on_text_delta = kwargs.get("on_text_delta")
        if self.stream_text and on_text_delta is not None:
            on_text_delta(self.stream_text)
        return self.output


def _output(text: str, *, artifact: bool = False) -> TurnOutput:
    tool_results: list[ToolResult] = []
    if artifact:
        tool_results.append(
            ToolResult(
                tool_call_id="tool-1",
                ok=True,
                artifacts=[
                    Artifact(
                        type=ArtifactType.DIFF,
                        path="README.md",
                        data={"patch": "@@ -1 +1 @@\n-old\n+new"},
                    )
                ],
            )
        )
    return TurnOutput(
        assistant_message=Message(
            role=Role.ASSISTANT,
            content=text,
            created_at=datetime.now(timezone.utc),
        ),
        tool_results=tool_results,
    )


def _server(tmp_path, output: TurnOutput, *, stream_text: str = "") -> GatewayServer:
    server = GatewayServer.__new__(GatewayServer)
    server.agent_name = "test"
    server.entry = SimpleNamespace(name="fake", provider="fake", model="fake")
    server.workspace = tmp_path
    server.active_skills = []
    server.memory_block = None
    server.session = SessionRuntime(session_id="test")
    server.skill_commands = {}
    server.orchestrator = _SilentOrchestrator(output, stream_text=stream_text)
    server._turn_lock = threading.Lock()
    server._send_lock = threading.Lock()
    server._system_prompt_for_session = lambda: ""
    return server


def _events_from_run(server: GatewayServer, text: str = "salut") -> list[dict]:
    left, right = socket.socketpair()
    chunks: list[str] = []
    try:
        right.settimeout(1)
        server._run_turn(left, text, threading.Event())
        while True:
            chunk = right.recv(4096).decode()
            if not chunk:
                break
            chunks.append(chunk)
            if '"type": "done"' in "".join(chunks):
                break
    finally:
        left.close()
        right.close()
    return [json.loads(line) for line in "".join(chunks).splitlines()]


def test_gateway_sends_final_assistant_when_no_delta_was_streamed(tmp_path) -> None:
    server = _server(tmp_path, _output("réponse finale"))
    left, right = socket.socketpair()
    try:
        right.settimeout(1)
        server._run_turn(left, "salut", threading.Event())

        payload = right.recv(4096).decode()
    finally:
        left.close()
        right.close()

    events = [json.loads(line) for line in payload.splitlines()]
    assert events == [
        {"text": "réponse finale", "type": "delta"},
        {"type": "done"},
    ]


def test_telegram_uses_final_assistant_when_no_delta_was_streamed(tmp_path) -> None:
    server = _server(tmp_path, _output("réponse telegram"))

    assert server.run_turn_for_telegram("salut") == "réponse telegram"


def test_gateway_appends_tool_artifacts_to_final_delta(tmp_path) -> None:
    server = _server(tmp_path, _output("patch prêt", artifact=True))
    left, right = socket.socketpair()
    try:
        right.settimeout(1)
        server._run_turn(left, "salut", threading.Event())

        payload = right.recv(4096).decode()
    finally:
        left.close()
        right.close()

    events = [json.loads(line) for line in payload.splitlines()]
    assert events[-1] == {"type": "done"}
    assert events[0]["type"] == "delta"
    assert "patch prêt" in events[0]["text"]
    assert "**Diff — `README.md`**" in events[0]["text"]
    assert "+new" in events[0]["text"]


def test_telegram_appends_tool_artifacts_to_final_response(tmp_path) -> None:
    server = _server(tmp_path, _output("patch telegram", artifact=True))

    response = server.run_turn_for_telegram("salut")

    assert "patch telegram" in response
    assert "**Diff — `README.md`**" in response
    assert "+new" in response


def test_gateway_streaming_appends_artifacts_without_repeating_answer(tmp_path) -> None:
    server = _server(tmp_path, _output("streamed answer", artifact=True), stream_text="streamed answer")
    left, right = socket.socketpair()
    try:
        right.settimeout(1)
        server._run_turn(left, "salut", threading.Event())

        payload = right.recv(4096).decode()
    finally:
        left.close()
        right.close()

    events = [json.loads(line) for line in payload.splitlines()]
    deltas = [event["text"] for event in events if event["type"] == "delta"]
    assert deltas[0] == "streamed answer"
    assert deltas[1].startswith("\n\n**Diff — `README.md`**")
    assert "streamed answer" not in deltas[1]


def test_gateway_agentic_watch_run_streams_events_and_report_artifact(tmp_path) -> None:
    def fake_search(args):
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="ok",
            data={
                "results": [
                    {
                        "title": "Marius release",
                        "url": "https://example.com/marius-release",
                        "content": f"Fresh result for {args['query']}",
                    }
                ]
            },
        )

    def fake_summary(_topic, _results, _metadata):
        return "Résumé veille: une nouveauté utile à suivre."

    server = _server(tmp_path, TurnOutput())
    tools = make_watch_tools(
        root=tmp_path / "watch",
        search_handler=fake_search,
        summarizer=fake_summary,
    )
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="fake", model="fake"),
        completion_text="J’ai lancé la veille et je te fais le récap.",
        tool_call_sequence=[
            [
                ToolCall(
                    id="call_add",
                    name="watch_add",
                    arguments={
                        "title": "Marius",
                        "query": "Marius updates",
                        "notify": "new",
                        "notify_min_score": 0.1,
                    },
                )
            ],
            [
                ToolCall(
                    id="call_run",
                    name="watch_run",
                    arguments={"id": "marius", "max_results": 1},
                )
            ],
        ],
    )
    server.orchestrator = RuntimeOrchestrator(
        provider=provider,
        tool_router=ToolRouter(list(tools.values())),
    )

    events = _events_from_run(server, "surveille Marius")

    assert [event["type"] for event in events] == [
        "tool_start",
        "tool_result",
        "tool_start",
        "tool_result",
        "delta",
        "done",
    ]
    assert events[0]["name"] == "watch_add"
    assert events[2]["name"] == "watch_run"
    deltas = [event["text"] for event in events if event["type"] == "delta"]
    assert deltas[0] == "J’ai lancé la veille et je te fais le récap."
    assert not any("**Rapport — `watch-run.md`**" in delta for delta in deltas)
    assert "novelty max" in server.session.state.turns[-1].tool_results[-1].summary
    assert "Résumé veille" in server.session.state.turns[-1].tool_results[-1].summary


def test_gateway_builtin_memories_command_returns_direct_response(tmp_path) -> None:
    server = _server(tmp_path, _output("ne doit pas répondre"))
    server.memory_store = MemoryStore(db_path=tmp_path / "memory.db")
    server.memory_store.add("Le projet utilise pytest")

    events = _events_from_run(server, "/memories")

    assert events[-1] == {"type": "done"}
    assert events[0]["type"] == "delta"
    assert "# Souvenirs" in events[0]["text"]
    assert "Le projet utilise pytest" in events[0]["text"]


def test_gateway_builtin_doctor_command_returns_report(tmp_path, monkeypatch) -> None:
    server = _server(tmp_path, _output("ne doit pas répondre"))
    server.memory_store = MemoryStore(db_path=tmp_path / "memory.db")
    monkeypatch.setattr("marius.config.doctor.run_doctor", lambda agent_name=None: [Section("Config")])

    events = _events_from_run(server, "/doctor")

    assert events[0]["type"] == "delta"
    assert "marius doctor" in events[0]["text"]
    assert events[-1] == {"type": "done"}


def test_gateway_builtin_command_wins_over_skill_command(tmp_path, monkeypatch) -> None:
    server = _server(tmp_path, _output("ne doit pas répondre"))
    server.memory_store = MemoryStore(db_path=tmp_path / "memory.db")
    server.skill_commands = {
        "doctor": SkillCommand(
            name="doctor",
            description="skill doctor",
            prompt="Utilise run_bash pour diagnostiquer.",
            skill_name="dev",
        )
    }
    monkeypatch.setattr("marius.config.doctor.run_doctor", lambda agent_name=None: [Section("Config")])

    events = _events_from_run(server, "/doctor")

    assert events[0]["type"] == "delta"
    assert "marius doctor" in events[0]["text"]
    assert "Utilise run_bash" not in events[0]["text"]
    assert events[-1] == {"type": "done"}


def test_gateway_builtin_dream_command_uses_dreaming_tool(tmp_path, monkeypatch) -> None:
    server = _server(tmp_path, _output("ne doit pas répondre"))
    server.memory_store = MemoryStore(db_path=tmp_path / "memory.db")
    server.active_skills = ["dev"]

    def fake_make_dreaming_tools(**kwargs):
        assert kwargs["memory_store"] is server.memory_store
        assert kwargs["entry"] is server.entry
        assert kwargs["active_skills"] == ["dev"]
        return {
            "dreaming_run": SimpleNamespace(
                handler=lambda _args: ToolResult(tool_call_id="", ok=True, summary="Dream OK")
            )
        }

    monkeypatch.setattr("marius.tools.dreaming.make_dreaming_tools", fake_make_dreaming_tools)

    events = _events_from_run(server, "/dream")

    assert events == [
        {"text": "Dream OK", "type": "delta"},
        {"type": "done"},
    ]
