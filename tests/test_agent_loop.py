"""Boucle agent : la réflexion est demandée à Gemini mais jamais renvoyée à l'utilisateur."""

from __future__ import annotations

from google.genai import types

from peche.agent import loop


class _FakeModels:
    def __init__(self, chunks):
        self._chunks = chunks
        self.config = None

    def generate_content_stream(self, *, model, contents, config):
        self.config = config
        return iter(self._chunks)


class _FakeClient:
    def __init__(self, chunks):
        self.models = _FakeModels(chunks)


def _chunk(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def test_thoughts_traced_but_not_streamed_to_user():
    client = _FakeClient(
        [
            _chunk(
                types.Part(text="je dois vérifier la météo", thought=True),
                types.Part(text="Bonjour"),
            )
        ]
    )
    history = [types.Content(role="user", parts=[types.Part.from_text(text="salut")])]

    events = list(
        loop._run_agent_turn(
            history, model="m", client=client, map_state=None
        )
    )

    texts = [e["text"] for e in events if e["type"] == "text"]
    assert texts == ["Bonjour"]
    assert client.models.config.thinking_config.include_thoughts is True
    assert client.models.config.thinking_config.thinking_budget == loop.THINKING_BUDGET
