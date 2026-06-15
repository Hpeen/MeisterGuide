"""Meister Guide entry point: tray icon, global hotkey, overlay window."""
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from meister_guide.theme.stylesheet import build_stylesheet
from meister_guide.overlay.window import OverlayWindow
from meister_guide.input.hotkey import GlobalHotkey

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
    painter.drawText(pix.rect(), 0x0084, "⚒")  # AlignCenter, crossed hammers
    painter.end()
    return QIcon(pix)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # live in the tray
    app.setStyleSheet(build_stylesheet())

    settings = QSettings(ORG, APP)
    overlay = OverlayWindow(settings)

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

    # Global hotkey
    hotkey = GlobalHotkey("Alt+Insert")
    hotkey.triggered.connect(overlay.toggle)
    app.installNativeEventFilter(hotkey)
    if not hotkey.register():
        tray.showMessage(
            "Meister Guide",
            "Could not register Alt+Insert (already in use?).",
            QSystemTrayIcon.Warning,
        )

    app.aboutToQuit.connect(hotkey.unregister)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
