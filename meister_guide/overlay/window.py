"""The Meister Guide overlay window (Phase 1 shell)."""
from PySide6.QtCore import Qt, QSettings, QPoint, QRect
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame, QComboBox,
)

import sys

from meister_guide.config.geometry import save_geometry, restore_geometry
from meister_guide.overlay.win32_topmost import (
    force_window_to_front,
    get_foreground_window,
    is_window_topmost,
    set_window_topmost,
)

_DEFAULT_RECT = QRect(200, 200, 460, 620)


class OverlayWindow(QWidget):
    def __init__(self, settings: QSettings, games=None):
        super().__init__()
        self._settings = settings
        self._drag_offset = None
        self._games = list(games) if games else []
        self.active_game = None
        # HWND of a fullscreen/always-on-top game we temporarily demoted so the
        # overlay can sit above it; restored when the overlay hides.
        self._demoted_hwnd = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # keeps it off the taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._build_ui()
        self._apply_saved_geometry()

    # ---- layout ---------------------------------------------------------
    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        spine = QFrame()
        spine.setObjectName("Spine")
        spine.setFixedWidth(4)
        outer.addWidget(spine)

        root = QWidget()
        root.setObjectName("OverlayRoot")
        outer.addWidget(root)

        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        col.addWidget(self._build_header())
        col.addWidget(self._build_disclaimer())
        col.addWidget(self._build_tabs(), 1)
        col.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(40)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(12, 0, 12, 0)

        title = QLabel("⚒ Meister Guide")  # crossed hammers
        title.setObjectName("HeaderTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        self.game_indicator = QLabel("● No game detected")
        self.game_indicator.setObjectName("GameIndicator")
        lay.addWidget(self.game_indicator)

        self.game_dropdown = QComboBox()
        self.game_dropdown.setObjectName("GameDropdown")
        self.game_dropdown.currentIndexChanged.connect(self._on_manual_pick)
        lay.addWidget(self.game_dropdown)
        self._populate_dropdown()

        self._header = header
        return header

    def _build_disclaimer(self) -> QWidget:
        # The overlay can only sit above games run in windowed / borderless mode;
        # exclusive fullscreen (e.g. Minecraft's F11) renders past it.
        bar = QLabel(
            "Tip: run your game in windowed or borderless mode so the overlay "
            "can show on top — exclusive fullscreen will cover it."
        )
        bar.setObjectName("Disclaimer")
        bar.setWordWrap(True)
        bar.setContentsMargins(12, 6, 12, 6)
        return bar

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        for name in ("Chat", "Guides", "Settings"):
            page = QLabel(f"{name} — coming in a later phase")
            page.setAlignment(Qt.AlignCenter)
            page.setContentsMargins(16, 16, 16, 16)
            tabs.addTab(page, name)
        return tabs

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setFixedHeight(32)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(12, 0, 8, 0)

        hint = QLabel("Alt+Insert to hide")
        lay.addWidget(hint)
        lay.addStretch(1)

        minimize = QPushButton("–")
        minimize.setFixedWidth(28)
        minimize.clicked.connect(self.hide)
        lay.addWidget(minimize)

        close = QPushButton("✕")
        close.setFixedWidth(28)
        close.clicked.connect(self.hide)
        lay.addWidget(close)
        return footer

    # ---- game selection -------------------------------------------------
    def _populate_dropdown(self):
        self.game_dropdown.blockSignals(True)
        self.game_dropdown.clear()
        self.game_dropdown.addItem("Select a game...", None)
        for game in self._games:
            self.game_dropdown.addItem(game.name, game.id)
        self.game_dropdown.blockSignals(False)

    def set_games(self, games):
        self._games = list(games)
        self._populate_dropdown()

    def _set_active(self, game, manual: bool):
        self.active_game = game
        if game is None:
            self.game_indicator.setText("● No game detected")
            self.game_dropdown.setVisible(True)
        else:
            suffix = " (manual)" if manual else ""
            self.game_indicator.setText(f"● Playing: {game.name}{suffix}")
            # Hide the picker on auto-detection; keep it on a manual pick so the
            # user can re-choose.
            self.game_dropdown.setVisible(manual)

    def set_detected_game(self, game):
        """Called by the detector. A detection always wins over a manual pick."""
        self._set_active(game, manual=False)

    def _on_manual_pick(self, index):
        game_id = self.game_dropdown.itemData(index)
        if game_id is None:
            return
        chosen = next((g for g in self._games if g.id == game_id), None)
        if chosen is not None:
            self._set_active(chosen, manual=True)

    # ---- geometry persistence ------------------------------------------
    def _apply_saved_geometry(self):
        rect = restore_geometry(self._settings)
        self.setGeometry(rect if rect is not None else _DEFAULT_RECT)

    def _persist_geometry(self):
        save_geometry(self._settings, self.geometry())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._persist_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._persist_geometry()

    def closeEvent(self, event):
        self._persist_geometry()
        super().closeEvent(event)

    # ---- drag by header -------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_header(event.position()):
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def _on_header(self, pos) -> bool:
        # pos is relative to the window; header sits in the top 40px past the spine.
        return pos.y() < self._header.height() and pos.x() >= 4

    # ---- toggle ---------------------------------------------------------
    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            # Capture the game BEFORE we steal the foreground, then drop it out
            # of the always-on-top band so our overlay can sit above a
            # fullscreen game (e.g. Minecraft). Restored in hideEvent.
            self._demote_foreground_game()
            self.show()
            self.raise_()
            self.activateWindow()
            # WS_EX_TOPMOST + raise_() lose to a borderless-fullscreen game that
            # owns the foreground, so re-assert topmost natively on every show.
            force_window_to_front(int(self.winId()))

    def hideEvent(self, event):
        # Covers Alt+Insert, the tray toggle, and the footer minimize/close
        # buttons — all routes that hide the overlay restore the game.
        self._restore_demoted_game()
        super().hideEvent(event)

    def _demote_foreground_game(self):
        if sys.platform != "win32":
            return
        fg = get_foreground_window()
        my_hwnd = int(self.winId())
        # Only touch a window that is *already* topmost (a fullscreen game or
        # another always-on-top app) so we never disturb ordinary windows.
        if fg and fg != my_hwnd and is_window_topmost(fg):
            set_window_topmost(fg, False)
            self._demoted_hwnd = fg

    def _restore_demoted_game(self):
        if self._demoted_hwnd:
            set_window_topmost(self._demoted_hwnd, True)
            self._demoted_hwnd = None
