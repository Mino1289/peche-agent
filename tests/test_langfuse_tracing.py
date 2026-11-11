"""Traçage Langfuse de la boucle agent (export OTel capturé en mémoire)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google.genai import types
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from peche import observability
from peche.agent import loop


def _chunk(*parts: types.Part, usage: tuple[int, int, int] | None = None):
    um = None
    if usage:
        um = SimpleNamespace(
            prompt_token_count=usage[0],
            candidates_token_count=usage[1],
            thoughts_token_count=0,
            total_token_count=usage[2],
            cached_content_token_count=None,
            tool_use_prompt_token_count=None,
        )
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=types.Content(role="model", parts=list(parts)),
                finish_reason="STOP",
            )
        ],
        usage_metadata=um,
    )


class _FakeModels:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    def generate_content_stream(self, *, model, contents, config):
        self.calls += 1
        step = self._scripted.pop(0)
        if isinstance(step, Exception):
            raise step
        return iter(step)


class _FakeClient:
    def __init__(self, scripted):
        self.models = _FakeModels(scripted)


@pytest.fixture
def spans():
    import uuid

    from langfuse import Langfuse

    exporter = InMemorySpanExporter()
    # Le SDK met ses ressources en cache par clé publique : une clé par test.
    client = Langfuse(
        public_key=f"pk-test-{uuid.uuid4().hex}",
        secret_key="sk-test",
        base_url="http://localhost:1",
        span_exporter=exporter,
    )
    observability.set_client(client)

    def collect():
        client.flush()
        return exporter.get_finished_spans()

    yield collect
    observability.set_client(None)


def _by_name(finished, name):
    return [s for s in finished if s.name == name]


def _attr(span, key):
    raw = span.attributes.get(f"langfuse.observation.{key}")
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return raw


def test_chat_turn_trace_tree(monkeypatch, spans):
    def fake_point_tool(pin_number=None):
        # Sous-observation créée en profondeur : doit se nicher sous le tool.
        with observability.observation(
            "resolve-point-context", as_type="retriever", input={"pin": pin_number}
        ) as obs:
            obs.update(output={"fishing_zone": {"no_zone": 28}})
        return {"pin_number": pin_number, "fishing_zone": {"no_zone": 28}}

    monkeypatch.setattr(loop, "TOOLS", {"get_point_info": fake_point_tool})
    client = _FakeClient(
        [
            [
                _chunk(
                    types.Part(
                        function_call=types.FunctionCall(
                            name="get_point_info", args={"pin_number": 1}
                        )
                    ),
                    usage=(120, 10, 130),
                )
            ],
            [_chunk(types.Part.from_text(text="Zone 28."), usage=(200, 5, 205))],
        ]
    )
    map_state = {
        "center": [-71.1, 48.4],
        "zoom": 9,
        "layers": [{"id": "plans_regpec", "visible": True}],
        "pins": [{"n": 1, "label": "Mon spot", "lon": -71.0, "lat": 48.4}],
    }

    events = list(
        loop.stream_chat(
            "Quelles règles au point 1 ?",
            history=[],
            client=client,
            map_state=map_state,
            locale="fr",
            api_key="AIza" + "x" * 35,
            session_id="sess-1",
        )
    )
    assert events[-1] == {"type": "done"}

    finished = spans()
    root = _by_name(finished, "chat-turn")[0]
    assert root.parent is None
    assert _attr(root, "type") == "agent"
    assert _attr(root, "input") == "Quelles règles au point 1 ?"
    assert _attr(root, "output") == "Zone 28."
    meta = {
        k.rsplit(".", 1)[-1]: json.loads(v)
        for k, v in root.attributes.items()
        if k.startswith("langfuse.observation.metadata.")
    }
    assert meta["status"] == "completed"
    assert meta["llm_calls"] == 2
    assert meta["input_tokens"] == 320
    assert meta["tools_called"] == ["get_point_info"]

    # Toutes les observations partagent session + tags.
    for s in finished:
        assert s.attributes["session.id"] == "sess-1"

    ctx = _by_name(finished, "load-map-context")[0]
    assert ctx.parent.span_id == root.context.span_id
    assert _attr(ctx, "output")["pins"][0]["label"] == "Mon spot"
    assert _attr(ctx, "output")["visible_layers"] == ["plans_regpec"]

    attempt = _by_name(finished, "run-agent-attempt")[0]
    assert attempt.parent.span_id == root.context.span_id

    gens = _by_name(finished, "generate-agent-step")
    assert len(gens) == 2  # une génération par appel modèle
    for g in gens:
        assert g.parent.span_id == attempt.context.span_id
        assert _attr(g, "type") == "generation"

    # 1re génération : input OpenAI-compatible avec system + user.
    first = next(g for g in gens if _attr(g, "usage_details")["input"] == 120)
    msgs = _attr(first, "input")
    assert [m["role"] for m in msgs] == ["system", "user"]
    out = _attr(first, "output")
    assert out["tool_calls"][0]["function"]["name"] == "get_point_info"
    assert json.loads(out["tool_calls"][0]["function"]["arguments"]) == {
        "pin_number": 1
    }

    # 2e génération : voit l'appel d'outil ET son résultat (role=tool, même id).
    second = next(g for g in gens if g is not first)
    msgs2 = _attr(second, "input")
    assert [m["role"] for m in msgs2] == ["system", "user", "assistant", "tool"]
    assert msgs2[3]["tool_call_id"] == msgs2[2]["tool_calls"][0]["id"]
    assert _attr(second, "output")["content"] == "Zone 28."

    tool = _by_name(finished, "tool-get_point_info")[0]
    assert _attr(tool, "type") == "tool"
    assert tool.parent.span_id == attempt.context.span_id  # frère des générations
    assert _attr(tool, "input") == {"pin_number": 1}
    retriever = _by_name(finished, "resolve-point-context")[0]
    assert retriever.parent.span_id == tool.context.span_id

    # La clé API (BYOK) ne doit apparaître nulle part.
    assert "AIza" not in json.dumps(
        [dict(s.attributes) for s in finished], default=str
    )


def test_attempt_span_has_input_and_output(spans):
    client = _FakeClient([[_chunk(types.Part.from_text(text="Bonjour."))]])
    list(loop.stream_chat("salut", history=[], client=client, session_id="s"))

    attempt = _by_name(spans(), "run-agent-attempt")[0]
    assert _attr(attempt, "input") == "salut"
    assert _attr(attempt, "output") == "Bonjour."


def test_tool_error_and_retry_are_flagged(monkeypatch, spans):
    monkeypatch.setattr(loop, "_RETRY_BACKOFF_S", 0)
    monkeypatch.setattr(loop, "TOOLS", {})
    client = _FakeClient(
        [
            RuntimeError("503 unavailable"),
            [
                _chunk(
                    types.Part(
                        function_call=types.FunctionCall(name="nope", args={})
                    )
                )
            ],
            [_chunk(types.Part.from_text(text="Désolé."))],
        ]
    )
    list(loop.stream_chat("test", history=[], client=client, session_id="s"))

    finished = spans()
    attempts = _by_name(finished, "run-agent-attempt")
    assert len(attempts) == 2
    failed = next(a for a in attempts if _attr(a, "level") == "ERROR")
    assert "503" in _attr(failed, "status_message")
    tool = _by_name(finished, "tool-nope")[0]
    assert _attr(tool, "level") == "ERROR"
    assert "inconnu" in _attr(tool, "status_message")


def test_disabled_tracing_is_noop(monkeypatch):
    observability.set_client(None)
    monkeypatch.setattr(loop, "TOOLS", {})
    client = _FakeClient([[_chunk(types.Part.from_text(text="ok"))]])
    events = list(loop.stream_chat("hi", history=[], client=client))
    assert [e["type"] for e in events] == ["text", "done"]


def test_mask_redacts_api_keys():
    key = "AIza" + "a" * 35
    out = observability._mask(
        data={"msg": f"key={key}", "api_key": "secret", "n": [1, {"x": key}]}
    )
    assert key not in json.dumps(out)
    assert out["api_key"] == "[REDACTED]"


def test_clip_truncates_large_payloads():
    big = {"blob": "x" * 500}
    assert observability.clip(big, limit=100).endswith("caractères au total]")
    assert observability.clip({"a": 1}, limit=100) == {"a": 1}
