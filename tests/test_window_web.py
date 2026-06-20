from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.settings import SettingsRepo


class OllamaStub:
    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]
    def chat(self, model, messages):
        return iter(())


def _window(tmp_path, key=""):
    db = tmp_path / "w.db"
    conn = connect(db)
    init_db(conn)
    QApplication.instance() or QApplication([])
    games = GamesRepo(conn)
    g = games.add("NoWiki", [], None)   # no wiki_url -> web is the only fallback
    repo = SettingsRepo(conn)
    if key:
        repo.set("brave_api_key", key)
    w = OverlayWindow(QSettings("MeisterGuide", "Web"),
                      games.list_games(), ArticlesRepo(conn), str(db), None,
                      OllamaStub(), settings_repo=repo, games_repo=games)
    w._set_active(g, manual=True)
    return w, repo


def test_web_enabled_reflects_settings(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    assert w._web_enabled() is True
    repo.set("web_fallback", "0")
    assert w._web_enabled() is False


def test_hits_answer_without_web(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._retrieve = lambda q: ([(1, "T")], [("T", "passage")])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web


def test_miss_with_web_enabled_starts_web_fetch(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert web and not answered


def test_miss_with_web_disabled_answers_anyway(tmp_path):
    w, repo = _window(tmp_path)   # user explicitly pauses web fallback
    repo.set("web_fallback", "0")
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web


def test_web_fetch_done_cancelled_restores_input(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._chat_cancelled = True
    started = []
    w._start_chat_worker = lambda: started.append(True)
    w._on_web_fetch_done("q", [])
    assert started == []
    assert w.chat_input.isEnabled()


def test_web_fetch_done_answers(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._chat_cancelled = False
    w._chat_view = [{"role": "user", "text": "q", "sources": []},
                    {"role": "assistant", "text": "", "sources": []}]
    w._retrieve = lambda q: ([(1, "T")], [("T", "p")])
    started = []
    w._start_chat_worker = lambda: started.append(True)
    w._on_web_fetch_done("q", [])
    assert started == [True]


def test_shutdown_cancels_active_web_worker(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    class FakeWorker:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True
    fw = FakeWorker()
    w._web_worker = fw
    w.shutdown()
    assert fw.cancelled


def test_hide_cancels_active_web_worker(tmp_path):
    from PySide6.QtGui import QHideEvent
    w, repo = _window(tmp_path, key="brv-123")
    class FakeWorker:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True
    fw = FakeWorker()
    w._web_worker = fw
    w.hideEvent(QHideEvent())
    assert fw.cancelled
    assert w._chat_cancelled is True


def test_settings_persists_brave_key_and_toggle(tmp_path):
    w, repo = _window(tmp_path)
    w.set_brave_key.setText("brv-xyz")
    w.set_web_fallback.setChecked(False)
    w._on_save_settings()
    assert repo.brave_api_key() == "brv-xyz"
    assert repo.get("web_fallback") == "0"


def test_web_enabled_by_default_without_key(tmp_path):
    w, repo = _window(tmp_path)            # no Brave key
    assert w._web_enabled() is True        # free DuckDuckGo, on by default
    repo.set("web_fallback", "0")
    assert w._web_enabled() is False
