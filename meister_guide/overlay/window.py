"""The Meister Guide overlay window (Phase 1 shell)."""
from PySide6.QtCore import Qt, QSettings, QPoint, QRect
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame,
)

from meister_guide.config.geometry import save_geometry, restore_geometry

_DEFAULT_RECT = QRect(200, 200, 460, 620)


class OverlayWindow(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self._settings = settings
        self._drag_offset = None

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

        self._header = header
        return header

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
            self.show()
            self.raise_()
            self.activateWindow()
