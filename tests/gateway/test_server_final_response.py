from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

from marius.config.doctor import Section
from marius.gateway.server import GatewayServer, _append_visible_history, _attached_image_artifacts
from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolCall, ToolResult
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig
from marius.kernel.runtime import RuntimeOrchestrator, TurnOutput
from marius.kernel.session import SessionRuntime
from marius.kernel.skills import SkillCommand
from marius.kernel.tool_router import ToolRouter
from marius.storage.memory_store import MemoryStore


class _SilentOrchestrator:
    def __init__(self, output: TurnOutput, *, stream_text: str = "") -> None:
        self.output = output
        self.stream_text = stream_text

    def run_turn(self, *_args, **kwargs) -> TurnOutput:
        on_text_delta = kwargs.get("on_text_delta")
        if self.stream_text and on_text_delta is not None:
            on_text_delta(self.stream_text)
        return self.output


class _ToolTraceOrchestrator:
    def __init__(self, output: TurnOutput) -> None:
        self.output = output

    def run_turn(self, *_args, **kwargs) -> TurnOutput:
        call = ToolCall(id="call-1", name="read_file", arguments={"path": "/tmp/demo.md"})
        kwargs["on_tool_start"](call)
        kwargs["on_tool_result"](
            call,
            ToolResult(tool_call_id="call-1", ok=True, summary="fichier lu"),
        )
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
    server._mirror_visible_to_telegram = lambda **_kwargs: None
    return server


def _events_from_run(server: GatewayServer, text: str = "salut", *, channel: str = "web") -> list[dict]:
    left, right = socket.socketpair()
    chunks: list[str] = []
    try:
        right.settimeout(1)
        server._run_turn(left, text, threading.Event(), channel)
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


def test_telegram_records_visible_history_in_canonical_file(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("réponse telegram"))

    assert server.run_turn_for_telegram("salut") == "réponse telegram"

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert [(m["role"], m["content"], m["channel"]) for m in history] == [
        ("user", "salut", "telegram"),
        ("assistant", "réponse telegram", "telegram"),
    ]


def test_gateway_cli_records_visible_history_in_canonical_file(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("réponse cli"))

    _events_from_run(server, "salut", channel="cli")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert [(m["role"], m["content"], m["channel"]) for m in history] == [
        ("user", "salut", "cli"),
        ("assistant", "réponse cli", "cli"),
    ]


def test_gateway_web_channel_records_visible_history_in_canonical_file(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("réponse web"))

    _events_from_run(server, "salut", channel="web")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert [(m["role"], m["content"], m["channel"]) for m in history] == [
        ("user", "salut", "web"),
        ("assistant", "réponse web", "web"),
    ]


def test_visible_history_persists_assistant_tool_metadata(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)

    _append_visible_history(
        "test",
        "assistant",
        "réponse",
        channel="web",
        tools=[{
            "name": "read_file",
            "target": "/tmp/demo.md",
            "ok": True,
            "summary": "fichier lu",
            "error": "",
            "extra": "ignored",
        }],
    )

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert history == [{
        "role": "assistant",
        "content": "réponse",
        "created_at": history[0]["created_at"],
        "channel": "web",
        "tools": [{
            "name": "read_file",
            "target": "/tmp/demo.md",
            "ok": True,
            "summary": "fichier lu",
            "error": "",
        }],
    }]


def test_gateway_web_channel_attaches_live_tool_trace_to_visible_history(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("réponse web"))
    server.orchestrator = _ToolTraceOrchestrator(_output("réponse web"))

    _events_from_run(server, "lis le fichier", channel="web")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert history[-1]["role"] == "assistant"
    assert history[-1]["tools"] == [{
        "name": "read_file",
        "target": "/tmp/demo.md",
        "ok": True,
        "summary": "fichier lu",
        "error": "",
    }]


def test_gateway_routine_channel_hides_prompt_from_visible_history(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("briefing du jour"))

    _events_from_run(server, "prompt long de routine", channel="routine")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert [(m["role"], m["content"], m["channel"]) for m in history] == [
        ("assistant", "briefing du jour", "routine"),
    ]


def test_gateway_task_channel_hides_internal_prompt_from_visible_history(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "web_history.json"
    monkeypatch.setattr("marius.gateway.server.web_history_path", lambda _agent: history_path)
    server = _server(tmp_path, _output("task livrée"))

    _events_from_run(server, "[Task Board]\nTask id: t_123\n...", channel="task")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert [(m["role"], m["content"], m["channel"]) for m in history] == [
        ("assistant", "task livrée", "task"),
    ]


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


def test_attached_image_artifacts_only_accept_workspace_uploads(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    upload = workspace / "uploads" / "demo.png"
    outside = tmp_path / "outside.png"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"png bytes")
    outside.write_bytes(b"png bytes")

    artifacts = _attached_image_artifacts(
        f"ok [fichier joint : {upload}]\nnon [fichier joint : {outside}]",
        workspace,
    )

    assert len(artifacts) == 1
    assert artifacts[0].type is ArtifactType.IMAGE
    assert artifacts[0].path == str(upload.resolve())
    assert artifacts[0].data["source"] == "user_attachment"


def test_gateway_uses_native_image_artifacts_when_local_vision_disabled(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    upload = workspace / "uploads" / "demo.jpg"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"jpg bytes")
    server = _server(workspace, _output("ok"))
    server.tool_router = ToolRouter([])

    artifacts = server._native_image_artifacts(f"[fichier joint : {upload}]")

    assert [artifact.path for artifact in artifacts] == [str(upload.resolve())]


def test_gateway_skips_native_image_artifacts_when_local_vision_enabled(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    upload = workspace / "uploads" / "demo.jpg"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"jpg bytes")
    server = _server(workspace, _output("ok"))
    from marius.kernel.tool_router import ToolDefinition, ToolEntry

    server.tool_router = ToolRouter([
        ToolEntry(
            definition=ToolDefinition(name="vision", description="vision", parameters={}),
            handler=lambda _args: ToolResult(tool_call_id="", ok=True),
        )
    ])

    assert server._native_image_artifacts(f"[fichier joint : {upload}]") == []
