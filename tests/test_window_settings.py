from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo, BACKEND_CLAUDE, BACKEND_OLLAMA
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


def test_defaults_to_ollama_backend(tmp_path):
    w, repo, hk = _window(tmp_path)
    assert repo.chat_backend() == BACKEND_OLLAMA
    assert w._chat_client is w._ollama
    assert w._model == "llama3"
    assert w.chat_input.isEnabled()


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
