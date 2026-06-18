from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import (
    SettingsRepo, BACKEND_CLAUDE, BACKEND_OLLAMA, BACKEND_AUTO,
)
from meister_guide.ai.claude_client import ClaudeClient


class OllamaStub:
    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]
    def chat(self, model, messages):
        return iter(())


class FakeHotkey:
    def __init__(self, ok=True):
        self.spec = None
        self._ok = ok
    def rebind(self, spec):
        self.spec = spec
        return self._ok


def _window(tmp_path, ollama=None, hotkey=None):
    conn = connect(tmp_path / "w.db")
    init_db(conn)
    QApplication.instance() or QApplication([])
    repo = SettingsRepo(conn)
    hk = hotkey or FakeHotkey()
    w = OverlayWindow(QSettings("MeisterGuide", "T8"), [], None, ":memory:", None,
                      ollama if ollama is not None else OllamaStub(),
                      settings_repo=repo, hotkey=hk)
    return w, repo, hk


def test_defaults_to_auto_local_without_key(tmp_path):
    # Default is Auto. With no Claude key, Auto behaves exactly like the old
    # local-only default: a single-backend chain pointing at Ollama.
    w, repo, hk = _window(tmp_path)
    assert repo.chat_backend() == BACKEND_AUTO
    assert [a[2] for a in w._backend_chain] == ["local"]
    assert w._chat_client is w._ollama
    assert w._model == "llama3"
    assert w.chat_input.isEnabled()


def test_auto_with_key_chain_claude_then_local(tmp_path):
    # Auto + a key prefers Claude, with Ollama queued as the offline backup.
    w, repo, hk = _window(tmp_path)
    repo.set("chat_backend", BACKEND_AUTO)
    repo.set("claude_api_key", "sk-test")
    repo.set("claude_model", "claude-sonnet-4-6")
    w._refresh_chat_backend()
    assert [a[2] for a in w._backend_chain] == ["online", "local"]
    assert isinstance(w._chat_client, ClaudeClient)
    assert w._model == "claude-sonnet-4-6"
    assert "offline backup ready" in w.chat_status.text()
    assert w.chat_input.isEnabled()


def test_always_local_chain_is_ollama_only(tmp_path):
    w, repo, hk = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)
    repo.set("claude_api_key", "sk-test")  # ignored in always-local mode
    w._refresh_chat_backend()
    assert [a[2] for a in w._backend_chain] == ["local"]
    assert w._chat_client is w._ollama


def test_save_switches_to_claude_with_key(tmp_path):
    w, repo, hk = _window(tmp_path)
    w.set_backend.setCurrentIndex(w.set_backend.findData(BACKEND_CLAUDE))
    w.set_api_key.setText("sk-test")
    w.set_model.setCurrentIndex(w.set_model.findData("claude-sonnet-4-6"))
    w._on_save_settings()
    assert repo.chat_backend() == BACKEND_CLAUDE
    assert repo.claude_api_key() == "sk-test"
    assert isinstance(w._chat_client, ClaudeClient)
    assert w._model == "claude-sonnet-4-6"
    assert w.chat_input.isEnabled()


def test_claude_backend_without_key_disables_chat(tmp_path):
    w, repo, hk = _window(tmp_path)
    repo.set("chat_backend", BACKEND_CLAUDE)
    repo.set("claude_api_key", "")
    w._refresh_chat_backend()
    assert not w.chat_input.isEnabled()
    assert "API key" in w.chat_status.text()
    assert w._chat_client is None


def test_apply_hotkey_validates_rebinds_and_persists(tmp_path):
    w, repo, hk = _window(tmp_path)
    w.set_hotkey.setText("Ctrl+Shift+M")
    w._on_apply_hotkey()
    assert hk.spec == "Ctrl+Shift+M"
    assert repo.get("hotkey") == "Ctrl+Shift+M"


def test_apply_invalid_hotkey_does_not_rebind_or_persist(tmp_path):
    w, repo, hk = _window(tmp_path)
    w.set_hotkey.setText("Alt+")          # modifier with no key
    w._on_apply_hotkey()
    assert hk.spec is None                 # never rebound
    assert repo.get("hotkey", "Alt+Insert") == "Alt+Insert"
    assert "Invalid" in w.set_hotkey_status.text()


def test_os_rejected_hotkey_still_persists(tmp_path):
    w, repo, hk = _window(tmp_path, hotkey=FakeHotkey(ok=False))
    w.set_hotkey.setText("Ctrl+Alt+G")
    w._on_apply_hotkey()
    assert repo.get("hotkey") == "Ctrl+Alt+G"   # saved for next launch
    assert "next launch" in w.set_hotkey_status.text()


# ---- offline fallback -------------------------------------------------------

def _pending_assistant_turn(w):
    """Put the window in mid-stream state: a user turn plus an empty assistant
    turn, as _begin_exchange would leave it just before tokens arrive."""
    w._chat_view = [
        {"role": "user", "text": "q", "sources": []},
        {"role": "assistant", "text": "", "sources": []},
    ]
    w._pending_messages = [("user", "q")]
    w._chat_cancelled = False


def test_error_before_any_token_falls_back_to_next_backend(tmp_path):
    w, repo, hk = _window(tmp_path)
    started = []
    w._start_chat_worker = lambda: started.append(w._attempt)
    w._backend_chain = [("claude", "opus", "online"), (w._ollama, "llama3", "local")]
    w._attempt = 0
    _pending_assistant_turn(w)
    w._on_chat_error("Connection refused")
    assert started == [1]                       # retried on the backup backend
    assert w._attempt == 1
    assert "locally with llama3" in w.chat_status.text()
    # The error text is NOT shown to the user — the fallback handled it.
    assert "[error" not in w._chat_view[-1]["text"]


def test_error_after_partial_stream_does_not_fall_back(tmp_path):
    w, repo, hk = _window(tmp_path)
    started = []
    w._start_chat_worker = lambda: started.append(w._attempt)
    w._backend_chain = [("claude", "opus", "online"), (w._ollama, "llama3", "local")]
    w._attempt = 0
    _pending_assistant_turn(w)
    w._chat_view[-1]["text"] = "Half an answer"   # tokens already streamed
    w._on_chat_error("stream dropped")
    assert started == []                          # no silent retry mid-answer
    assert "[error: stream dropped]" in w._chat_view[-1]["text"]


def test_error_on_last_backend_surfaces_error(tmp_path):
    w, repo, hk = _window(tmp_path)
    started = []
    w._start_chat_worker = lambda: started.append(w._attempt)
    w._backend_chain = [(w._ollama, "llama3", "local")]   # single backend
    w._attempt = 0
    _pending_assistant_turn(w)
    w._on_chat_error("Ollama down")
    assert started == []
    assert "[error: Ollama down]" in w._chat_view[-1]["text"]
