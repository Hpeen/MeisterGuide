"""Meister Guide entry point: tray icon, global hotkey, overlay window."""
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from meister_guide.theme.stylesheet import build_stylesheet
from meister_guide.theme.fonts import load_fonts
from meister_guide.overlay.window import OverlayWindow
from meister_guide.input.hotkey import GlobalHotkey
from meister_guide.db.database import default_db_path, connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.chat import ChatRepo
from meister_guide.db.settings import SettingsRepo
from meister_guide.ai.ollama_client import OllamaClient
from meister_guide.detector.detector import GameDetector

ORG = "MeisterGuide"
APP = "MeisterGuide"


def _make_tray_icon() -> QIcon:
    """A simple brass hammer glyph on a dark square, drawn at runtime so we
    don't depend on an asset file in Phase 1."""
    pix = QPixmap(32, 32)
    pix.fill(QColor("#1C1208"))
    painter = QPainter(pix)
    painter.setPen(QColor("#E07B39"))
    font = QFont("Segoe UI Symbol", 18)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "⚒")  # crossed hammers
    painter.end()
    return QIcon(pix)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # live in the tray
    load_fonts()                          # register bundled fonts first
    app.setStyleSheet(build_stylesheet())

    settings = QSettings(ORG, APP)

    conn = connect(default_db_path())
    init_db(conn)
    games_repo = GamesRepo(conn)
    games_repo.seed_defaults()
    games_repo.reconcile_builtin_games()  # upgrade a stale Minecraft process list
    articles_repo = ArticlesRepo(conn)
    chat_repo = ChatRepo(conn)
    settings_repo = SettingsRepo(conn)
    ollama_client = OllamaClient()

    # Build the hotkey from the stored spec (falling back to the default if a
    # saved value is somehow unparseable) so the Settings panel can rebind it.
    hotkey_spec = settings_repo.get("hotkey", "Alt+Insert")
    try:
        hotkey = GlobalHotkey(hotkey_spec)
    except ValueError:
        hotkey = GlobalHotkey("Alt+Insert")

    overlay = OverlayWindow(settings, games_repo.list_games(),
                            articles_repo=articles_repo,
                            db_path=default_db_path(),
                            chat_repo=chat_repo,
                            ollama_client=ollama_client,
                            settings_repo=settings_repo,
                            hotkey=hotkey)

    detector = GameDetector(games_provider=games_repo.list_games)
    detector.detected.connect(overlay.set_detected_game)

    # Tray
    tray = QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("Meister Guide")
    menu = QMenu()
    act_show = QAction("Show Overlay")
    act_show.triggered.connect(overlay.toggle)
    act_quit = QAction("Quit")
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_show)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: overlay.toggle()
        if reason == QSystemTrayIcon.DoubleClick
        else None
    )
    tray.show()

    # Global hotkey (created above from the stored spec; register it now)
    hotkey.triggered.connect(overlay.toggle)
    app.installNativeEventFilter(hotkey)
    if not hotkey.register():
        tray.showMessage(
            "Meister Guide",
            f"Could not register {hotkey_spec} (already in use?).",
            QSystemTrayIcon.Warning,
        )

    detector.start()

    app.aboutToQuit.connect(hotkey.unregister)
    app.aboutToQuit.connect(detector.stop)
    app.aboutToQuit.connect(overlay.shutdown)  # stop chat/ingest threads
    app.aboutToQuit.connect(settings.sync)  # flush geometry once on quit
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
