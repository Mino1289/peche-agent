"""Tests pour peche.conversations.store."""

from google.genai import types

from peche.conversations.store import _title_from_text


def test_title_from_text_truncation():
    long = "a" * 80
    title = _title_from_text(long)
    assert len(title) <= 60
    assert title.endswith("…")


def test_title_from_text_empty():
    assert _title_from_text("   ") == "Nouvelle conversation"


def test_conversation_crud(tmp_db):
    cid = tmp_db.create_conversation()
    assert cid
    meta = tmp_db.get_conversation(cid)
    assert meta is not None
    assert meta["title"] == "Nouvelle conversation"

    tmp_db.append_exchange(
        cid,
        "Quel est le niveau du Lac Kénogami ?",
        "Voici les stations.",
        [{"name": "get_hydromet_for_waterbody", "args": {}, "result": {}}],
    )
    msgs = tmp_db.load_messages(cid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tools"][0]["name"] == "get_hydromet_for_waterbody"

    convs = tmp_db.list_conversations(query="Kénogami")
    assert len(convs) == 1
    assert "Kénogami" in convs[0]["title"]

    assert tmp_db.rename_conversation(cid, "Lac Kénogami") is True
    assert tmp_db.get_conversation(cid)["title"] == "Lac Kénogami"

    history = [
        types.Content(role="user", parts=[types.Part(text="Bonjour")]),
    ]
    tmp_db.save_gemini_history(cid, history)
    loaded = tmp_db.load_gemini_history(cid)
    assert len(loaded) == 1
    assert loaded[0].role == "user"

    assert tmp_db.delete_conversation(cid) is True
    assert tmp_db.get_conversation(cid) is None
