"""Key/value app settings on the `settings` table (created in Phase 2). Used
from Phase 7 on for the chat-backend choice and Claude API credentials. Values
are stored as text; callers coerce as needed."""

BACKEND_OLLAMA = "ollama"
BACKEND_CLAUDE = "claude"
BACKEND_AUTO = "auto"

# Defaults returned when a key has never been written. Auto is the default:
# prefer Claude when an API key is set (deeper answers), otherwise stay fully
# local on Ollama — and fall back to local automatically if Claude can't be
# reached. No key means it behaves exactly like the old Ollama default.
_DEFAULTS = {
    "chat_backend": BACKEND_AUTO,
    "claude_api_key": "",
    "claude_model": "claude-opus-4-8",
    "dock_edge": "right",
}


class SettingsRepo:
    def __init__(self, conn):
        self._conn = conn

    def get(self, key, default=None):
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is not None:
            return row[0]
        return _DEFAULTS.get(key, default)

    def set(self, key, value, commit=True):
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, "" if value is None else str(value)),
        )
        if commit:
            self._conn.commit()

    # Convenience accessors for the chat backend selection.
    def chat_backend(self):
        return self.get("chat_backend")

    def claude_api_key(self):
        return self.get("claude_api_key")

    def claude_model(self):
        return self.get("claude_model")
