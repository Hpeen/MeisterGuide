# Meister Guide — Phase 1: Overlay Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows app that launches silently to the system tray and toggles a transparent, always-on-top, draggable "rustic workshop" overlay with `Alt+Insert`, remembering its size and position between sessions.

**Architecture:** Pure PySide6 widgets styled with QSS (no embedded web view). A native Win32 `RegisterHotKey` global hotkey is caught via a `QAbstractNativeEventFilter`. Window geometry persists through `QSettings`. The full rustic theme is applied in this phase so later phases inherit it.

**Tech Stack:** Python 3.11+, PySide6, pywin32 not required (we use `ctypes` for Win32), QSettings for geometry.

---

## File Structure

```
meister_guide/
  __init__.py
  main.py                  app entry: QApplication, tray, hotkey wiring
  theme/
    __init__.py
    palette.py             PALETTE dict of hex colors (testable)
    stylesheet.py          build_stylesheet() -> QSS string (testable)
    woodgrain.py           WOODGRAIN_DATA_URI base64 SVG noise (constant)
  overlay/
    __init__.py
    window.py              OverlayWindow: frameless translucent always-on-top
  input/
    __init__.py
    hotkey.py              parse_hotkey() (testable) + GlobalHotkey (Win32)
  config/
    __init__.py
    geometry.py            save/restore window geometry via QSettings (testable)
tests/
  test_palette.py
  test_stylesheet.py
  test_hotkey.py
  test_geometry.py
requirements.txt
ARCHITECTURE.md
README.md
devlogs/
  001-the-shell.md
```

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `meister_guide/__init__.py`
- Create: `meister_guide/theme/__init__.py`
- Create: `meister_guide/overlay/__init__.py`
- Create: `meister_guide/input/__init__.py`
- Create: `meister_guide/config/__init__.py`
- Create: `tests/__init__.py`
- Create: `ARCHITECTURE.md`
- Create: `README.md`

- [ ] **Step 1: Create `requirements.txt`**

```
PySide6==6.7.2
psutil==6.0.0
requests==2.32.3
beautifulsoup4==4.12.3
pytest==8.2.2
```

- [ ] **Step 2: Create empty package markers**

Create each of these as empty files:
`meister_guide/__init__.py`, `meister_guide/theme/__init__.py`,
`meister_guide/overlay/__init__.py`, `meister_guide/input/__init__.py`,
`meister_guide/config/__init__.py`, `tests/__init__.py`.

- [ ] **Step 3: Write `ARCHITECTURE.md`**

```markdown
# Architecture

Meister Guide is a Windows desktop overlay built with **Python + PySide6**.

## Why this stack
- **Global hotkey over fullscreen games:** native Win32 `RegisterHotKey` via `ctypes`,
  caught through a `QAbstractNativeEventFilter`. Survives exclusive-fullscreen games
  where higher-level keyboard hooks drop events.
- **Transparent always-on-top overlay:** Qt window flags
  (`FramelessWindowHint | WindowStaysOnTopHint | Tool`) + `WA_TranslucentBackground`.
  Reliable on Windows without an embedded browser.
- **UI styling:** QSS (Qt Style Sheets) render the full "rustic workshop" theme —
  wood-grain background, custom scrollbars, burnt-sienna left spine, chat bubbles.
- **Storage:** `QSettings` for window geometry (Phase 1); SQLite at
  `%APPDATA%\MeisterGuide\meister.db` for everything else (Phase 2+).
- **AI:** local Ollama over HTTP (Phase 4). Claude API is a stubbed future option.

## Modules
- `theme/` — palette constants, QSS builder, wood-grain asset.
- `overlay/` — the overlay window and its tab widgets.
- `input/` — global hotkey parsing and Win32 registration.
- `config/` — window geometry persistence.
- `db/`, `scraper/`, `ai/`, `detector/` — added in later phases.
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Meister Guide

A rustic gaming companion overlay with offline guides and a local AI assistant
("Meister"), powered by Ollama. Windows desktop, built with Python + PySide6.

## Setup
1. Install Python 3.11+.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. Run: `python -m meister_guide.main`

## Hotkey
`Alt + Insert` toggles the overlay (rebindable in Settings, later phase).

## AI (later phase)
Meister uses [Ollama](https://ollama.com) running locally at
`http://localhost:11434`. Install Ollama and `ollama pull llama3`.

## Tests
`pytest -q`
```

- [ ] **Step 5: Install and verify**

Run: `pip install -r requirements.txt && python -c "import PySide6; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt meister_guide tests ARCHITECTURE.md README.md
git commit -m "chore: scaffold Phase 1 project structure"
```

---

### Task 2: Theme palette constants

**Files:**
- Create: `meister_guide/theme/palette.py`
- Test: `tests/test_palette.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_palette.py
from meister_guide.theme.palette import PALETTE

def test_palette_has_all_roles_with_hex_values():
    expected = {
        "background": "#1C1208",
        "panel": "#2A1C0E",
        "surface_raised": "#3B2512",
        "accent_primary": "#C1440E",
        "accent_warm": "#E07B39",
        "accent_gold": "#D4A843",
        "text_primary": "#F0E2C8",
        "text_muted": "#8C7355",
        "border": "#5C3D1E",
        "success": "#7A9E4E",
        "error": "#C0392B",
    }
    assert PALETTE == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_palette.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/theme/palette.py
"""Rustic workshop color palette. Source of truth for all UI colors."""

PALETTE = {
    "background": "#1C1208",      # deep charred walnut
    "panel": "#2A1C0E",           # dark mahogany
    "surface_raised": "#3B2512",  # warm teak
    "accent_primary": "#C1440E",  # burnt sienna (brand)
    "accent_warm": "#E07B39",     # amber ember
    "accent_gold": "#D4A843",     # aged brass
    "text_primary": "#F0E2C8",    # parchment
    "text_muted": "#8C7355",      # weathered oak
    "border": "#5C3D1E",          # dark oak grain
    "success": "#7A9E4E",         # forest moss
    "error": "#C0392B",           # deep ember
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_palette.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/palette.py tests/test_palette.py
git commit -m "feat: add rustic workshop color palette"
```

---

### Task 3: Wood-grain texture constant

**Files:**
- Create: `meister_guide/theme/woodgrain.py`

- [ ] **Step 1: Create the texture constant**

A subtle base64-encoded SVG fractal-noise tile used as a faint background overlay.

```python
# meister_guide/theme/woodgrain.py
"""Subtle wood-grain noise tile as a base64 data URI for QSS backgrounds."""
import base64

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
    '<filter id="n">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.9 0.02" '
    'numOctaves="2" seed="7"/>'
    '<feColorMatrix type="saturate" values="0"/>'
    '</filter>'
    '<rect width="120" height="120" filter="url(#n)" opacity="0.05"/>'
    '</svg>'
)

WOODGRAIN_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(
    _SVG.encode("utf-8")
).decode("ascii")
```

- [ ] **Step 2: Verify it imports and produces a data URI**

Run: `python -c "from meister_guide.theme.woodgrain import WOODGRAIN_DATA_URI; print(WOODGRAIN_DATA_URI[:30])"`
Expected: prints `data:image/svg+xml;base64,` followed by characters.

- [ ] **Step 3: Commit**

```bash
git add meister_guide/theme/woodgrain.py
git commit -m "feat: add subtle wood-grain texture constant"
```

---

### Task 4: QSS stylesheet builder

**Files:**
- Create: `meister_guide/theme/stylesheet.py`
- Test: `tests/test_stylesheet.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stylesheet.py
from meister_guide.theme.stylesheet import build_stylesheet
from meister_guide.theme.palette import PALETTE

def test_stylesheet_includes_core_colors_and_widgets():
    qss = build_stylesheet()
    # brand colors present
    assert PALETTE["background"] in qss
    assert PALETTE["accent_primary"] in qss
    assert PALETTE["accent_warm"] in qss
    # styles the widgets we rely on
    assert "QPushButton" in qss
    assert "QScrollBar:vertical" in qss
    # custom thin scrollbar width
    assert "width: 6px" in qss
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stylesheet.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/theme/stylesheet.py
"""Builds the global QSS stylesheet from the palette."""
from meister_guide.theme.palette import PALETTE


def build_stylesheet() -> str:
    p = PALETTE
    return f"""
    QWidget {{
        color: {p['text_primary']};
        font-family: 'Segoe UI';
        font-size: 13px;
    }}
    #OverlayRoot {{
        background-color: {p['background']};
        border: 1px solid {p['border']};
        border-radius: 4px;
    }}
    #Spine {{
        background-color: {p['accent_primary']};
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }}
    #Header {{
        background-color: {p['panel']};
    }}
    #HeaderTitle {{
        font-family: 'Palatino Linotype', 'Book Antiqua', Georgia, serif;
        font-size: 16px;
        font-weight: 700;
        color: {p['accent_gold']};
    }}
    #GameIndicator {{
        color: {p['text_muted']};
    }}
    QPushButton {{
        background-color: {p['surface_raised']};
        border: 1px solid {p['accent_primary']};
        border-radius: 4px;
        padding: 4px 10px;
        color: {p['text_primary']};
    }}
    QPushButton:hover {{
        background-color: {p['accent_primary']};
        color: {p['background']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p['text_muted']};
        padding: 6px 14px;
        font-family: 'Segoe UI';
    }}
    QTabBar::tab:selected {{
        color: {p['accent_gold']};
        border-bottom: 3px solid {p['accent_warm']};
    }}
    QTabWidget::pane {{
        border: none;
    }}
    #Footer {{
        background-color: {p['panel']};
        color: {p['text_muted']};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p['border']};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stylesheet.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/stylesheet.py tests/test_stylesheet.py
git commit -m "feat: add QSS stylesheet builder for rustic theme"
```

---

### Task 5: Hotkey parsing

**Files:**
- Create: `meister_guide/input/hotkey.py`
- Test: `tests/test_hotkey.py`

This task implements only the **pure, testable** parser. The Win32 registration class
is added in Task 7 (it requires a live window and can't be unit-tested honestly).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkey.py
from meister_guide.input.hotkey import parse_hotkey, MOD_ALT, MOD_CONTROL, MOD_SHIFT

def test_parse_alt_insert():
    mods, vk = parse_hotkey("Alt+Insert")
    assert mods == MOD_ALT
    assert vk == 0x2D  # VK_INSERT

def test_parse_ctrl_shift_g():
    mods, vk = parse_hotkey("Ctrl+Shift+G")
    assert mods == (MOD_CONTROL | MOD_SHIFT)
    assert vk == ord("G")

def test_parse_is_case_insensitive_on_modifiers():
    mods, vk = parse_hotkey("alt+insert")
    assert mods == MOD_ALT
    assert vk == 0x2D
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkey.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/input/hotkey.py
"""Global hotkey parsing (pure) + Win32 registration (added in Task 7)."""

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MOD_NAMES = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

# Named virtual-key codes we support beyond single characters.
_VK_NAMES = {
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "space": 0x20,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def parse_hotkey(spec: str):
    """Parse a string like 'Alt+Insert' into (modifiers, virtual_key_code).

    Raises ValueError if the key part is unknown.
    """
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    mods = 0
    key = None
    for part in parts:
        low = part.lower()
        if low in _MOD_NAMES:
            mods |= _MOD_NAMES[low]
        else:
            key = part
    if key is None:
        raise ValueError(f"No key in hotkey spec: {spec!r}")
    low = key.lower()
    if low in _VK_NAMES:
        return mods, _VK_NAMES[low]
    if len(key) == 1:
        return mods, ord(key.upper())
    raise ValueError(f"Unknown key in hotkey spec: {spec!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hotkey.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/input/hotkey.py tests/test_hotkey.py
git commit -m "feat: add hotkey string parser"
```

---

### Task 6: Window geometry persistence

**Files:**
- Create: `meister_guide/config/geometry.py`
- Test: `tests/test_geometry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geometry.py
from PySide6.QtCore import QSettings, QRect
from meister_guide.config.geometry import save_geometry, restore_geometry

def _settings(tmp_path):
    # Use an isolated INI file so the test never touches the real registry.
    return QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)

def test_restore_returns_none_when_unset(tmp_path):
    s = _settings(tmp_path)
    assert restore_geometry(s) is None

def test_save_then_restore_roundtrips(tmp_path):
    s = _settings(tmp_path)
    save_geometry(s, QRect(100, 120, 480, 640))
    rect = restore_geometry(s)
    assert rect == QRect(100, 120, 480, 640)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_geometry.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/config/geometry.py
"""Persist the overlay window's size and position via QSettings."""
from PySide6.QtCore import QSettings, QRect

_KEY = "overlay/geometry"


def save_geometry(settings: QSettings, rect: QRect) -> None:
    settings.setValue(
        _KEY, [rect.x(), rect.y(), rect.width(), rect.height()]
    )
    settings.sync()


def restore_geometry(settings: QSettings):
    """Return a QRect, or None if nothing has been saved yet."""
    raw = settings.value(_KEY)
    if not raw:
        return None
    x, y, w, h = (int(v) for v in raw)
    return QRect(x, y, w, h)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_geometry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/config/geometry.py tests/test_geometry.py
git commit -m "feat: persist overlay window geometry via QSettings"
```

---

### Task 7: Win32 global hotkey registration

**Files:**
- Modify: `meister_guide/input/hotkey.py` (append the `GlobalHotkey` class)

This is native Win32 code that needs a live event loop; it is verified by running the
app in Task 9, not by a unit test.

- [ ] **Step 1: Append the `GlobalHotkey` class to `meister_guide/input/hotkey.py`**

```python
# --- append to meister_guide/input/hotkey.py ---
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

_WM_HOTKEY = 0x0312
_HOTKEY_ID = 1


class GlobalHotkey(QAbstractNativeEventFilter, QObject):
    """Registers a system-wide hotkey via Win32 RegisterHotKey and emits
    `triggered` when pressed. Install on the QApplication and call register()."""

    triggered = Signal()

    def __init__(self, spec: str = "Alt+Insert"):
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self._mods, self._vk = parse_hotkey(spec)
        self._registered = False

    def register(self) -> bool:
        # MOD_NOREPEAT (0x4000) avoids auto-repeat floods.
        ok = ctypes.windll.user32.RegisterHotKey(
            None, _HOTKEY_ID, self._mods | 0x4000, self._vk
        )
        self._registered = bool(ok)
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            self._registered = False

    def rebind(self, spec: str) -> bool:
        self.unregister()
        self._mods, self._vk = parse_hotkey(spec)
        return self.register()

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self.triggered.emit()
        return False, 0
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from meister_guide.input.hotkey import GlobalHotkey; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Run the existing hotkey tests (no regressions)**

Run: `pytest tests/test_hotkey.py -v`
Expected: PASS (3 tests).

- [ ] **Step 4: Commit**

```bash
git add meister_guide/input/hotkey.py
git commit -m "feat: add Win32 global hotkey registration"
```

---

### Task 8: Overlay window

**Files:**
- Create: `meister_guide/overlay/window.py`

Builds the frameless, translucent, always-on-top overlay matching the spec layout:
left burnt-sienna spine, draggable header with title + game indicator, Chat/Guides/
Settings tabs (placeholder content this phase), footer with the hotkey hint plus
minimize and close buttons. Geometry restores on show and saves on move/resize/close.

- [ ] **Step 1: Create `meister_guide/overlay/window.py`**

```python
# meister_guide/overlay/window.py
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
        return pos.y() <= self._header.height() and pos.x() >= 4

    # ---- toggle ---------------------------------------------------------
    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from meister_guide.overlay.window import OverlayWindow; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: add overlay window shell with themed layout"
```

---

### Task 9: App entry — tray + hotkey wiring

**Files:**
- Create: `meister_guide/main.py`

- [ ] **Step 1: Create `meister_guide/main.py`**

```python
# meister_guide/main.py
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
    painter.drawText(pix.rect(), 0x0084, "⚒")  # AlignCenter
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
```

- [ ] **Step 2: Run the app and verify behavior (manual)**

Run: `python -m meister_guide.main`

Verify each:
1. No window appears on launch; a hammer tray icon shows in the system tray.
2. Pressing `Alt+Insert` shows the overlay; pressing again hides it.
3. The overlay is frameless, dark, with a burnt-sienna strip down the left edge,
   a header reading "Meister Guide", three tabs (Chat / Guides / Settings), and a
   footer reading "Alt+Insert to hide" with minimize and close buttons.
4. Dragging the header moves the window.
5. While a fullscreen or borderless game is focused, `Alt+Insert` still toggles the
   overlay on top of it. (Test with Minecraft if available.)
6. Close the overlay, move it, reopen the app: it returns to its last size/position.
7. Tray right-click -> Quit exits the app.

Expected: all seven behaviors hold.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add meister_guide/main.py
git commit -m "feat: wire tray, global hotkey, and overlay into app entry"
```

---

### Task 10: Phase 1 devlog

**Files:**
- Create: `devlogs/001-the-shell.md`

- [ ] **Step 1: Write the devlog (playful, informative, no emojis)**

```markdown
# Devlog 001 - The Shell

So. Day one of Meister Guide and I did the thing every game-overlay tutorial
quietly skips: getting a window to float on top of an actual fullscreen game
without the OS slapping it back down. Turns out the magic words are
FramelessWindowHint + WindowStaysOnTopHint + the translucent-background flag,
and suddenly I have a little dark panel hovering over everything like it owns
the place.

The hotkey was the spicy part. I went with Alt+Insert, and instead of some
library that breaks the second a game grabs the keyboard, I'm calling the raw
Windows RegisterHotKey function through ctypes. It registers the combo at the OS
level, so even when a game is hogging input, Windows still taps me on the
shoulder with a WM_HOTKEY message. I catch that with a native event filter and
flip the overlay on or off. Felt illegal. It is not.

Also gave the whole thing its personality already: deep charred-walnut
background, a burnt-sienna leather "spine" running down the left edge, brass
heading text, that warm parchment color for reading. It is supposed to feel like
a carpenter's guild journal, not a settings menu, and honestly it kind of does.

Right now the Chat / Guides / Settings tabs are just polite "coming later" labels,
and the window remembers where you left it via QSettings. Next up: the database
and actually noticing when Minecraft is running. Onward.
```

- [ ] **Step 2: Commit**

```bash
git add devlogs/001-the-shell.md
git commit -m "docs: add Phase 1 devlog"
```

---

## Self-Review

**Spec coverage (Phase 1 scope):**
- Silent launch to tray — Task 9. ✓
- `Alt+Insert` toggles overlay (rebindable later) — Tasks 5, 7, 9. ✓
- Always-on-top over fullscreen — Task 8 flags + Task 9 verify step 5. ✓
- Semi-transparent dark rustic theme — Tasks 2, 3, 4, 8. ✓
- Resizable / draggable by header — Task 8. ✓
- Close + minimize-to-tray — Task 8 footer, Task 9 tray. ✓
- Remembers size/position — Task 6, Task 8. ✓
- Left burnt-sienna spine, header, tabs, footer layout — Task 8. ✓
- Devlog — Task 10. ✓

Deferred to later phases (correctly out of Phase 1 scope): opacity slider, real tab
content, game detection logic, SQLite. The "Playing: Minecraft" indicator exists as a
static label here and gets wired to detection in Phase 2.

**Placeholder scan:** No TBDs. The tab pages are intentionally labeled placeholders for
this phase, not plan placeholders — every step has complete code.

**Type consistency:** `parse_hotkey` returns `(mods, vk)` and is consumed that way in
`GlobalHotkey`. `save_geometry`/`restore_geometry` signatures match their test and the
window usage. `OverlayWindow.toggle()` is the name connected in `main.py` and the tray.
`build_stylesheet()` name matches across stylesheet module, test, and `main.py`.
