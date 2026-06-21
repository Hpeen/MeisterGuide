# tests/test_shell_window.py
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, QRect
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo, BACKEND_OLLAMA, BACKEND_AUTO
from meister_guide.config.dock import PANEL_WIDTH, MARGIN
from meister_guide.db.games import Game  # dataclass: id, name, process_names, wiki_url


class OllamaStub:
    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]
    def chat(self, model, messages):
        return iter(())


def _window(tmp_path, edge="right"):
    conn = connect(tmp_path / "w.db")
    init_db(conn)
    QApplication.instance() or QApplication([])
    repo = SettingsRepo(conn)
    repo.set("dock_edge", edge)
    w = OverlayWindow(QSettings("MeisterGuide", "T10"), [], None, ":memory:",
                      None, OllamaStub(), settings_repo=repo)
    return w, repo


def test_apply_dock_sets_width_and_edge(tmp_path):
    w, repo = _window(tmp_path, edge="right")
    screen = QRect(0, 0, 1920, 1080)
    w._apply_dock(screen)                 # explicit screen so no display needed
    assert w.width() == PANEL_WIDTH
    assert w._dock_edge == "right"
    assert w.x() == 1920 - MARGIN - PANEL_WIDTH


def test_snap_on_release_persists_edge(tmp_path):
    w, repo = _window(tmp_path, edge="right")
    screen = QRect(0, 0, 1920, 1080)
    # Simulate the window having been dragged to the far left.
    w._snap_to_nearest(window_center_x=120, screen=screen)
    assert w._dock_edge == "left"
    assert repo.get("dock_edge") == "left"
    assert w.x() == MARGIN


def _games():
    return [Game(id=1, name="Minecraft", process_names=["javaw.exe"], wiki_url=None),
            Game(id=2, name="Terraria", process_names=["terraria.exe"], wiki_url=None)]


def test_detected_game_updates_pill(tmp_path):
    w, repo = _window(tmp_path)
    w.set_games(_games())
    w.set_detected_game(_games()[0])
    assert "Minecraft" in w.game_pill.text()
    w.set_detected_game(None)
    assert "No game" in w.game_pill.text()


def test_game_pill_menu_manual_pick(tmp_path):
    w, repo = _window(tmp_path)
    w.set_games(_games())
    w._on_manual_pick_game(2)            # what the menu action calls
    assert w.active_game is not None and w.active_game.id == 2
    assert "Terraria" in w.game_pill.text()


def test_tab_order_and_default(tmp_path):
    w, repo = _window(tmp_path)
    titles = [w._tabs.tabText(i) for i in range(w._tabs.count())]
    assert titles[0] == "Wiki"
    assert titles[1] == "Ask Meister"
    assert w._tabs.currentIndex() == 0       # default landing = Wiki


def test_footer_copy_adapts_to_backend(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)
    repo.set("web_fallback", "0")          # local chat AND web paused -> offline
    w._refresh_footer()
    assert "offline mode" in w.footer_note.text().lower()
    repo.set("chat_backend", BACKEND_AUTO)
    repo.set("claude_api_key", "sk-x")
    w._refresh_footer()
    assert "web-augmented" in w.footer_note.text().lower()


def test_footer_web_augmented_when_only_web_fallback_on(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)   # local chat backend
    repo.set("web_fallback", "1")              # but web fallback on (default)
    w._refresh_footer()
    assert "web-augmented" in w.footer_note.text().lower()


class _FakeWorker:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_hide_does_not_cancel_bulk_ingest(tmp_path):
    # Hiding the overlay (to go back to the game) must NOT stop the long-running
    # guide download — it runs in the background and only stops on app quit.
    from PySide6.QtGui import QHideEvent
    w, repo = _window(tmp_path)
    fw = _FakeWorker()
    w._ingest_worker = fw
    w.hideEvent(QHideEvent())
    assert fw.cancelled is False


def test_shutdown_cancels_bulk_ingest(tmp_path):
    # On real app quit the download must be cancelled and torn down.
    w, repo = _window(tmp_path)
    fw = _FakeWorker()
    w._ingest_worker = fw
    w.shutdown()
    assert fw.cancelled is True
