"""Stockage SQLite des conversations Streamlit / API."""

from __future__ import annotations

import base64
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.genai import types

from peche.reglements.sync import DATA_DIR

DB_PATH = DATA_DIR / "conversations.db"

_BYTES_MARKER = "__bytes_b64__"


def _json_default(obj: object) -> object:
    if isinstance(obj, bytes):
        return {_BYTES_MARKER: base64.b64encode(obj).decode("ascii")}
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_object_hook(item: dict) -> dict | bytes:
    if set(item.keys()) == {_BYTES_MARKER}:
        return base64.b64decode(item[_BYTES_MARKER])
    return item


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _title_from_text(text: str, max_len: int = 60) -> str:
    line = " ".join(text.strip().split())
    if len(line) <= max_len:
        return line or "Nouvelle conversation"
    return line[: max_len - 1] + "…"


class ConversationStore:
    """Accès SQLite aux conversations et à l'historique Gemini."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    tools_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE TABLE IF NOT EXISTS gemini_history (
                    conversation_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                    ON messages(conversation_id, id);
                """
            )

    def create_conversation(self, title: str | None = None) -> str:
        cid = uuid.uuid4().hex
        now = _utc_now()
        t = title or "Nouvelle conversation"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cid, t, now, now),
            )
            conn.execute(
                "INSERT INTO gemini_history (conversation_id, payload_json) VALUES (?, ?)",
                (cid, "[]"),
            )
        return cid

    def list_conversations(self, limit: int = 50, query: str | None = None) -> list[dict]:
        sql = """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
        """
        params: list[object] = []
        if query and query.strip():
            sql += " WHERE c.title LIKE ?"
            params.append(f"%{query.strip()}%")
        sql += " ORDER BY c.updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def rename_conversation(self, conversation_id: str, title: str) -> bool:
        title = title.strip()
        if not title:
            return False
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conversation_id),
            )
            return cur.rowcount > 0

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute(
                "DELETE FROM gemini_history WHERE conversation_id = ?", (conversation_id,)
            )
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            return cur.rowcount > 0

    def load_messages(self, conversation_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, text, tools_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id
                """,
                (conversation_id,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            msg: dict = {"role": r["role"], "text": r["text"]}
            if r["tools_json"]:
                msg["tools"] = json.loads(r["tools_json"])
            out.append(msg)
        return out

    def load_gemini_history(self, conversation_id: str) -> list[types.Content]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM gemini_history WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if not row:
            return []
        raw = json.loads(row["payload_json"], object_hook=_json_object_hook)
        if not raw:
            return []
        out: list[types.Content] = []
        for item in raw:
            try:
                out.append(types.Content.model_validate(item))
            except Exception:  # noqa: BLE001
                continue
        return out

    def save_gemini_history(
        self, conversation_id: str, history: list[types.Content]
    ) -> None:
        payload = json.dumps(
            [c.model_dump() for c in history],
            ensure_ascii=False,
            default=_json_default,
        )
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE gemini_history SET payload_json = ? WHERE conversation_id = ?",
                (payload, conversation_id),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

    def append_exchange(
        self,
        conversation_id: str,
        user_text: str,
        assistant_text: str,
        tools_log: list[dict] | None = None,
    ) -> None:
        now = _utc_now()
        tools_json = json.dumps(tools_log, ensure_ascii=False, default=str) if tools_log else None
        with self._connect() as conn:
            conv = conn.execute(
                "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if conv and conv["title"] == "Nouvelle conversation" and user_text.strip():
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (_title_from_text(user_text), now, conversation_id),
                )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, text, tools_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, "user", user_text, None, now),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, text, tools_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, "assistant", assistant_text, tools_json, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

    def touch(self, conversation_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (_utc_now(), conversation_id),
            )
