"""Chat persistence over the Phase 2 chat_sessions / chat_messages tables."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatSession:
    id: int
    title: Optional[str]
    started_at: str


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatRepo:
    def __init__(self, conn):
        self._conn = conn

    def create_session(self, game_id=None, title=None) -> int:
        cur = self._conn.execute(
            "INSERT INTO chat_sessions (game_id, title) VALUES (?, ?)",
            (game_id, title),
        )
        self._conn.commit()
        return cur.lastrowid

    def set_title(self, session_id, title) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        self._conn.commit()

    def add_message(self, session_id, role, content) -> int:
        cur = self._conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_sessions(self):
        rows = self._conn.execute(
            "SELECT id, title, started_at FROM chat_sessions ORDER BY id DESC"
        ).fetchall()
        return [ChatSession(r[0], r[1], r[2]) for r in rows]

    def get_messages(self, session_id):
        rows = self._conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [ChatMessage(r[0], r[1]) for r in rows]
