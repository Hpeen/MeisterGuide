# tests/test_shell_window.py
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, QRect
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo
from meister_guide.config.dock import PANEL_WIDTH, MARGIN


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
