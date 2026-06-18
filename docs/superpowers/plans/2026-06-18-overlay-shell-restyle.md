# Overlay Shell & Theme Foundation (Phase 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the overlay shell to the carpenter's-journal design — woodgrain panel + leather spine (custom painting), bundled fonts, a docked panel snappable to either screen edge, and restyled header/tab-bar/footer — without touching tab contents or backend logic.

**Architecture:** Colours live in `theme/palette.py`, fonts in `theme/fonts.py` (loaded from bundled OFL `.ttf` in `assets/fonts/`), and the panel/spine are drawn in `theme/painters.py` via `QPainter.paintEvent`. Window geometry is computed by pure helpers in `config/dock.py` (`dock_rect`, `nearest_edge`) so it is unit-testable without a display; `OverlayWindow` consumes them to dock/snap/mirror. The dock edge persists via the existing SQLite `SettingsRepo`.

**Tech Stack:** Python 3.12, PySide6 6.7.2 (Qt 6.7), pytest (run headless with `QT_QPA_PLATFORM=offscreen`), `requests` for the one-time font fetch.

**Conventions for every test run in this plan:**
- Prefix: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8`
- Runner: `py -3 -m pytest`
- Full suite baseline before starting: **143 passing**.

**Spec:** `docs/superpowers/specs/2026-06-18-overlay-shell-restyle-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `meister_guide/theme/palette.py` | All colour tokens (expanded; old keys kept as aliases) |
| `meister_guide/theme/fonts.py` | **new** — register bundled fonts, role→family map, fallbacks |
| `assets/fonts/*.ttf` | **new** — bundled OFL font files |
| `meister_guide/theme/painters.py` | **new** — `paint_panel(widget, painter)` + `paint_spine(...)` |
| `meister_guide/theme/stylesheet.py` | QSS rewritten to new tokens/fonts/object names |
| `meister_guide/config/dock.py` | **new** — `dock_rect`, `nearest_edge` pure helpers |
| `meister_guide/overlay/window.py` | Docking/snap/mirror, header pills+menu, tab rename/reorder, footer, painter wiring |
| `meister_guide/main.py` | Call `load_fonts()`; read + pass `dock_edge` |
| `meister_guide/db/settings.py` | `dock_edge` default |
| `tests/test_dock.py` | **new** — dock helpers |
| `tests/test_fonts.py` | **new** — font loader fallback |
| `tests/test_shell_window.py` | **new** — docking application, header pills/menu, tabs, footer |
| `tests/test_painters.py` | **new** — paint smoke tests |
| `tests/test_settings_repo.py` | add `dock_edge` default assertion |
| `devlogs/010-the-frame.md` | **new** — phase devlog |

---

## Task 1: Expand colour palette tokens

**Files:**
- Modify: `meister_guide/theme/palette.py`
- Test: `tests/test_palette.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_palette.py
from meister_guide.theme.palette import PALETTE


def test_new_design_tokens_present():
    # A representative slice of the handoff token set.
    for key in (
        "walnut_base", "walnut_mid", "walnut_light",
        "spine_top", "spine_mid", "spine_bottom",
        "brass_bright", "brass_mid", "brass_dark", "brass_deep",
        "parchment", "parchment_mid", "parchment_dim", "parchment_muted",
        "parchment_ghost", "ink_dim",
        "user_bubble_bg", "user_bubble_border",
        "ai_bubble_bg", "ai_bubble_border",
        "green_online", "warning_text",
    ):
        assert key in PALETTE, f"missing token {key}"
        assert PALETTE[key]


def test_legacy_keys_still_resolve():
    # Old code (stylesheet.py, woodgrain) references these — keep them working.
    for key in ("background", "panel", "surface_raised", "accent_primary",
                "accent_warm", "accent_gold", "text_primary", "text_muted",
                "border", "success", "error"):
        assert key in PALETTE and PALETTE[key]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_palette.py -v`
Expected: FAIL — `missing token walnut_base`.

- [ ] **Step 3: Implement the expanded palette**

```python
# meister_guide/theme/palette.py
"""Rustic carpenter's-journal palette. Source of truth for all UI colors.

New design tokens come from the Phase-10 design handoff. Legacy keys
(background, panel, …) are kept as aliases so existing QSS keeps working."""

PALETTE = {
    # --- walnut panel ---
    "walnut_base": "#1a110b",
    "walnut_mid": "#251810",
    "walnut_light": "#1f150d",
    # --- leather spine ---
    "spine_top": "#8a4423",
    "spine_mid": "#6e3318",
    "spine_bottom": "#7a3a1e",
    # --- brass ramp ---
    "brass_bright": "#e0bd66",
    "brass_mid": "#c8a14a",
    "brass_dark": "#b8923f",
    "brass_deep": "#6b4f1d",
    # --- parchment text ---
    "parchment": "#e8dcc6",
    "parchment_mid": "#d8cbb0",
    "parchment_dim": "#b8a988",
    "parchment_muted": "#a89878",
    "parchment_ghost": "#9c8a66",
    "ink_dim": "#7a6a4f",
    # --- chat bubbles (used in Phase 11, defined now) ---
    "user_bubble_bg": "rgba(122,58,30,0.32)",
    "user_bubble_border": "rgba(200,110,70,0.35)",
    "ai_bubble_bg": "rgba(0,0,0,0.26)",
    "ai_bubble_border": "rgba(200,161,74,0.18)",
    # --- status ---
    "green_online": "#8fd058",
    "warning_text": "#b06a4a",

    # --- legacy aliases (do not remove; referenced by older code) ---
    "background": "#1a110b",      # -> walnut_base
    "panel": "#251810",           # -> walnut_mid
    "surface_raised": "#3B2512",
    "accent_primary": "#8a4423",  # -> spine_top
    "accent_warm": "#E07B39",
    "accent_gold": "#e0bd66",     # -> brass_bright
    "text_primary": "#e8dcc6",    # -> parchment
    "text_muted": "#9c8a66",      # -> parchment_ghost
    "border": "#5C3D1E",
    "success": "#8fd058",
    "error": "#C0392B",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_palette.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/palette.py tests/test_palette.py
git commit -m "feat: expand palette to full design token set (legacy keys aliased)"
```

---

## Task 2: Bundle + load fonts

**Files:**
- Create: `assets/fonts/` (the three `.ttf` files)
- Create: `meister_guide/theme/fonts.py`
- Test: `tests/test_fonts.py`

- [ ] **Step 1: Fetch the OFL font files**

Run this one-time fetch (writes three files into `assets/fonts/`):

```bash
py -3 - <<'PY'
import os, urllib.request
os.makedirs("assets/fonts", exist_ok=True)
files = {
    "PirataOne-Regular.ttf":
        "https://github.com/google/fonts/raw/main/ofl/pirataone/PirataOne-Regular.ttf",
    "Archivo.ttf":
        "https://github.com/google/fonts/raw/main/ofl/archivo/Archivo%5Bwdth,wght%5D.ttf",
    "SplineSansMono.ttf":
        "https://github.com/google/fonts/raw/main/ofl/splinesansmono/SplineSansMono%5Bwght%5D.ttf",
}
for name, url in files.items():
    dest = os.path.join("assets", "fonts", name)
    urllib.request.urlretrieve(url, dest)
    print(name, os.path.getsize(dest), "bytes")
PY
```

Expected: three files printed with non-trivial byte counts (>20 KB each).
If a URL 404s, find the file under https://github.com/google/fonts/tree/main/ofl/<family> and update the URL, then re-run. (Archivo & Spline Sans Mono are variable fonts — Qt 6.7 loads them fine.)

- [ ] **Step 2: Write the failing test**

```python
# tests/test_fonts.py
from PySide6.QtWidgets import QApplication
from meister_guide.theme import fonts


def _app():
    return QApplication.instance() or QApplication([])


def test_roles_have_families_after_load():
    _app()
    resolved = fonts.load_fonts()  # registers bundled ttf, returns role->family
    for role in ("display", "body", "mono"):
        assert role in resolved
        assert isinstance(resolved[role], str) and resolved[role]


def test_missing_font_file_falls_back(tmp_path):
    _app()
    # Point the loader at an empty dir so nothing registers; must still return
    # sane fallback families, never raise.
    resolved = fonts.load_fonts(assets_dir=tmp_path)
    assert resolved["display"]  # some serif fallback
    assert resolved["body"]
    assert resolved["mono"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_fonts.py -v`
Expected: FAIL — `ModuleNotFoundError: meister_guide.theme.fonts` / `AttributeError`.

- [ ] **Step 4: Implement the font loader**

```python
# meister_guide/theme/fonts.py
"""Registers the bundled OFL fonts with Qt and maps UI roles to family names.

Roles: display (Pirata One headings), body (Archivo copy), mono (Spline Sans
Mono labels). If a file is missing or fails to register, the role falls back to
a sensible system family so the app never hard-fails on a font."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase

_DEFAULT_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# role -> (filename, fallback family)
_FONTS = {
    "display": ("PirataOne-Regular.ttf", "Georgia"),
    "body": ("Archivo.ttf", "Segoe UI"),
    "mono": ("SplineSansMono.ttf", "Consolas"),
}

_resolved: dict[str, str] = {}


def load_fonts(assets_dir=None) -> dict:
    """Register bundled fonts; return {role: family}. Idempotent-safe to call
    once at startup."""
    base = Path(assets_dir) if assets_dir is not None else _DEFAULT_ASSETS
    resolved = {}
    for role, (filename, fallback) in _FONTS.items():
        family = fallback
        path = base / filename
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(fid) if fid != -1 else []
            if families:
                family = families[0]
        resolved[role] = family
    _resolved.clear()
    _resolved.update(resolved)
    return resolved


def family(role: str) -> str:
    """Family for a role; falls back to the declared system family if fonts were
    never loaded."""
    if role in _resolved:
        return _resolved[role]
    return _FONTS.get(role, ("", "Segoe UI"))[1]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_fonts.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add assets/fonts meister_guide/theme/fonts.py tests/test_fonts.py
git commit -m "feat: bundle and load Pirata One / Archivo / Spline Sans Mono with fallbacks"
```

---

## Task 3: Dock geometry pure helpers

**Files:**
- Create: `meister_guide/config/dock.py`
- Test: `tests/test_dock.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dock.py
from PySide6.QtCore import QRect
from meister_guide.config.dock import dock_rect, nearest_edge, PANEL_WIDTH, MARGIN


def test_dock_rect_right_edge():
    screen = QRect(0, 0, 1920, 1080)
    r = dock_rect(screen, "right")
    assert r.width() == PANEL_WIDTH
    assert r.height() == 1080 - 2 * MARGIN
    assert r.top() == MARGIN
    assert r.right() == 1920 - 1 - MARGIN  # MARGIN gap from screen's right edge


def test_dock_rect_left_edge():
    screen = QRect(0, 0, 1920, 1080)
    r = dock_rect(screen, "left")
    assert r.left() == MARGIN
    assert r.width() == PANEL_WIDTH


def test_dock_rect_respects_screen_offset():
    screen = QRect(1920, 0, 1280, 1024)  # second monitor to the right
    r = dock_rect(screen, "left")
    assert r.left() == 1920 + MARGIN


def test_nearest_edge_picks_by_midpoint():
    screen = QRect(0, 0, 1920, 1080)
    assert nearest_edge(100, screen) == "left"
    assert nearest_edge(1800, screen) == "right"
    assert nearest_edge(960, screen) == "right"  # exact midpoint -> right (tie)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_dock.py -v`
Expected: FAIL — `ModuleNotFoundError: meister_guide.config.dock`.

- [ ] **Step 3: Implement the helpers**

```python
# meister_guide/config/dock.py
"""Pure geometry helpers for the docked overlay panel. No Qt widgets here so
these stay unit-testable without a display."""
from PySide6.QtCore import QRect

PANEL_WIDTH = 432   # 30px spine + 402px body
MARGIN = 18         # gap from screen edges (top/bottom and the docked side)

VALID_EDGES = ("left", "right")


def normalize_edge(edge) -> str:
    return edge if edge in VALID_EDGES else "right"


def dock_rect(screen: QRect, edge: str) -> QRect:
    """Panel rectangle for the given screen geometry + edge."""
    edge = normalize_edge(edge)
    height = screen.height() - 2 * MARGIN
    top = screen.top() + MARGIN
    if edge == "left":
        left = screen.left() + MARGIN
    else:
        left = screen.right() + 1 - MARGIN - PANEL_WIDTH
    return QRect(left, top, PANEL_WIDTH, height)


def nearest_edge(window_center_x: int, screen: QRect) -> str:
    """Which edge a window centred at window_center_x should snap to."""
    midpoint = screen.left() + screen.width() / 2
    return "left" if window_center_x < midpoint else "right"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_dock.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/config/dock.py tests/test_dock.py
git commit -m "feat: pure dock geometry helpers (dock_rect, nearest_edge)"
```

---

## Task 4: `dock_edge` setting default + persistence

**Files:**
- Modify: `meister_guide/db/settings.py:10-14` (the `_DEFAULTS` dict)
- Test: `tests/test_settings_repo.py` (add a test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings_repo.py`:

```python
def test_dock_edge_default_is_right(tmp_path):
    repo = _repo(tmp_path)
    assert repo.get("dock_edge") == "right"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_settings_repo.py::test_dock_edge_default_is_right -v`
Expected: FAIL — returns `None`, not `"right"`.

- [ ] **Step 3: Add the default**

In `meister_guide/db/settings.py`, add `"dock_edge": "right",` to `_DEFAULTS`:

```python
_DEFAULTS = {
    "chat_backend": BACKEND_AUTO,
    "claude_api_key": "",
    "claude_model": "claude-opus-4-8",
    "dock_edge": "right",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_settings_repo.py -v`
Expected: PASS (all settings tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/settings.py tests/test_settings_repo.py
git commit -m "feat: dock_edge setting (default right)"
```

---

## Task 5: Spine painter

**Files:**
- Create: `meister_guide/theme/painters.py`
- Test: `tests/test_painters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_painters.py
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QPixmap, QPainter
from meister_guide.theme import painters


def _app():
    return QApplication.instance() or QApplication([])


def test_paint_spine_does_not_raise():
    _app()
    pm = QPixmap(30, 600)
    pm.fill()
    p = QPainter(pm)
    try:
        painters.paint_spine(p, 30, 600, edge="right")
        painters.paint_spine(p, 30, 600, edge="left")
    finally:
        p.end()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_painters.py -v`
Expected: FAIL — `ModuleNotFoundError: meister_guide.theme.painters`.

- [ ] **Step 3: Implement the spine painter**

```python
# meister_guide/theme/painters.py
"""Custom QPainter routines for the woodgrain body panel and leather spine.
Values mirror the Phase-10 design handoff CSS. `edge` is which screen edge the
panel is docked to; when docked left the layout mirrors so the spine always
faces inward."""
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPainter, QBrush

CORNER = 13.0
SPINE_W = 30


def _c(r, g, b, a=255):
    return QColor(r, g, b, a)


def paint_spine(painter: QPainter, w: int, h: int, edge: str = "right"):
    """Draw the leather spine into a w×h region whose top-left is (0,0).
    Rounded corners sit on the OUTER side (screen edge); for edge='right' the
    spine is on the panel's left so its rounded corners are on the left."""
    painter.setRenderHint(QPainter.Antialiasing, True)
    rounded_left = (edge == "right")  # spine on left -> round left corners

    # Leather vertical gradient.
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, _c(0x8a, 0x44, 0x23))
    grad.setColorAt(0.5, _c(0x6e, 0x33, 0x18))
    grad.setColorAt(1.0, _c(0x7a, 0x3a, 0x1e))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRect(0, 0, w, h)

    # Centred dotted stitching: 7px dash, 8px gap.
    painter.setBrush(_c(0xf7, 0xe0, 0xbe, 115))
    x = w / 2 - 1
    y = 0
    while y < h:
        painter.drawRect(QRectF(x, y, 2, 7))
        y += 15

    # Two brass studs, inset 18px top and bottom.
    for cy in (18, h - 18):
        rg = QRadialGradient(QPointF(w / 2 - 1, cy - 1), 5)
        rg.setColorAt(0.0, _c(0xff, 0xe7, 0xa6))
        rg.setColorAt(0.55, _c(0xb8, 0x92, 0x3f))
        rg.setColorAt(1.0, _c(0x6b, 0x4f, 0x1d))
        painter.setBrush(QBrush(rg))
        painter.drawEllipse(QPointF(w / 2, cy), 4, 4)

    # Inner edge shadow on the inward side.
    shade = QLinearGradient(0, 0, w, 0)
    if rounded_left:
        shade.setColorAt(0.85, _c(0, 0, 0, 0))
        shade.setColorAt(1.0, _c(0, 0, 0, 115))
    else:
        shade.setColorAt(0.0, _c(0, 0, 0, 115))
        shade.setColorAt(0.15, _c(0, 0, 0, 0))
    painter.setBrush(QBrush(shade))
    painter.drawRect(0, 0, w, h)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_painters.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/painters.py tests/test_painters.py
git commit -m "feat: leather spine painter"
```

---

## Task 6: Body panel painter

**Files:**
- Modify: `meister_guide/theme/painters.py`
- Test: `tests/test_painters.py` (add a test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_painters.py`:

```python
def test_paint_panel_does_not_raise():
    _app()
    pm = QPixmap(402, 600)
    pm.fill()
    p = QPainter(pm)
    try:
        painters.paint_panel(p, 402, 600, edge="right")
        painters.paint_panel(p, 402, 600, edge="left")
    finally:
        p.end()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_painters.py::test_paint_panel_does_not_raise -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'paint_panel'`.

- [ ] **Step 3: Implement the body panel painter**

Append to `meister_guide/theme/painters.py`:

```python
def _vlines(painter, w, h, step, line_w, color):
    """Approximates a repeating-linear-gradient of vertical grain lines."""
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    x = 0
    while x < w:
        painter.drawRect(QRectF(x, 0, line_w, h))
        x += step


def paint_panel(painter: QPainter, w: int, h: int, edge: str = "right"):
    """Draw the charred-walnut body panel into a w×h region at (0,0). Rounded
    corners sit on the inward side (away from the screen edge)."""
    painter.setRenderHint(QPainter.Antialiasing, True)

    # 1. Base diagonal gradient.
    base = QLinearGradient(0, 0, w, h * 0.2)
    base.setColorAt(0.0, _c(0x25, 0x18, 0x10))
    base.setColorAt(0.55, _c(0x1a, 0x11, 0x0b))
    base.setColorAt(1.0, _c(0x1f, 0x15, 0x0d))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(base))
    painter.drawRect(0, 0, w, h)

    # 2-5. Layered grain (coarse -> micro).
    _vlines(painter, w, h, 37, 1, _c(0, 0, 0, 33))
    _vlines(painter, w, h, 23, 2, _c(128, 86, 48, 15))
    _vlines(painter, w, h, 13, 1, _c(0, 0, 0, 56))
    _vlines(painter, w, h, 6, 1, _c(86, 60, 38, 28))

    # 6. Top/bottom edge vignette.
    vig = QLinearGradient(0, 0, 0, h)
    vig.setColorAt(0.0, _c(255, 200, 140, 13))
    vig.setColorAt(0.09, _c(0, 0, 0, 0))
    vig.setColorAt(0.91, _c(0, 0, 0, 0))
    vig.setColorAt(1.0, _c(0, 0, 0, 82))
    painter.setBrush(QBrush(vig))
    painter.drawRect(0, 0, w, h)

    # Inner top highlight.
    painter.setBrush(_c(255, 225, 160, 20))
    painter.drawRect(QRectF(0, 0, w, 1))
```

Note on rounded corners: corner rounding is applied at the widget level by
clipping the widget to a rounded path before calling these painters (Task 7), so
`paint_panel`/`paint_spine` themselves draw plain rectangles.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_painters.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/painters.py tests/test_painters.py
git commit -m "feat: woodgrain body panel painter"
```

---

## Task 7: Dock the window + snap + mirror

**Files:**
- Modify: `meister_guide/overlay/window.py` (constructor, geometry, drag-release, spine/panel widgets)
- Test: `tests/test_shell_window.py` (new)

This task replaces the free-floating geometry with docking. The painters are
wired into the `Spine` widget and the `OverlayRoot` widget via `paintEvent`, and
both are clipped to rounded corners on the correct side for `_dock_edge`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py -v`
Expected: FAIL — `AttributeError: 'OverlayWindow' object has no attribute '_apply_dock'`.

- [ ] **Step 3: Implement docking in `window.py`**

3a. Add imports near the other imports:

```python
from PySide6.QtGui import QPainter, QPainterPath, QRegion
from meister_guide.config.dock import (
    dock_rect, nearest_edge, normalize_edge, PANEL_WIDTH,
)
from meister_guide.theme import painters
```

3b. In `__init__`, after `self._settings_repo = settings_repo`, add:

```python
        self._dock_edge = normalize_edge(
            settings_repo.get("dock_edge", "right") if settings_repo else "right")
```

3c. Add these methods to `OverlayWindow` (anywhere among the geometry methods):

```python
    def _current_screen_geometry(self):
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.screenAt(self.geometry().center()) \
            or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _apply_dock(self, screen=None):
        screen = screen if screen is not None else self._current_screen_geometry()
        self.setFixedWidth(PANEL_WIDTH)
        self.setGeometry(dock_rect(screen, self._dock_edge))
        self._sync_layout_for_edge()

    def _snap_to_nearest(self, window_center_x=None, screen=None):
        screen = screen if screen is not None else self._current_screen_geometry()
        cx = window_center_x if window_center_x is not None \
            else self.geometry().center().x()
        self._dock_edge = nearest_edge(cx, screen)
        if self._settings_repo is not None:
            self._settings_repo.set("dock_edge", self._dock_edge)
        self.setGeometry(dock_rect(screen, self._dock_edge))
        self._sync_layout_for_edge()

    def _sync_layout_for_edge(self):
        # Spine faces inward: edge 'right' -> spine on left (index 0); edge
        # 'left' -> spine on right (last). Reorder the outer layout + tell the
        # widgets which side to round.
        spine_left = (self._dock_edge == "right")
        self._spine.set_edge(self._dock_edge)
        self._root_panel.set_edge(self._dock_edge)
        self._outer.removeWidget(self._spine)
        self._outer.removeWidget(self._root_panel)
        if spine_left:
            self._outer.addWidget(self._spine)
            self._outer.addWidget(self._root_panel)
        else:
            self._outer.addWidget(self._root_panel)
            self._outer.addWidget(self._spine)
```

3d. Replace the free-floating geometry hooks. In `_build_ui`, keep a reference to
the outer layout and the spine/panel as custom painter widgets:

Replace the body of `_build_ui` up to `col.addWidget(self._build_header())` with:

```python
    def _build_ui(self):
        self._outer = QHBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self._spine = _SpineWidget()
        self._spine.setFixedWidth(painters.SPINE_W)

        self._root_panel = _PanelWidget()
        self._root_panel.setObjectName("OverlayRoot")

        # order set by _sync_layout_for_edge(); add both now
        self._outer.addWidget(self._spine)
        self._outer.addWidget(self._root_panel)

        col = QVBoxLayout(self._root_panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._build_header())
        col.addWidget(self._build_tabs(), 1)
        col.addWidget(self._build_footer())
```

(Note: the disclaimer bar widget is intentionally dropped — do not add
`self._build_disclaimer()`. Leave the `_build_disclaimer` method in place but
unused, or delete it.)

3e. Add the two painter widget classes at module top (after `_DEFAULT_RECT`):

```python
class _PanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._edge = "right"

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        painters.paint_panel(p, self.width(), self.height(), self._edge)
        p.end()


class _SpineWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._edge = "right"

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        painters.paint_spine(p, self.width(), self.height(), self._edge)
        p.end()
```

3f. Replace `_apply_saved_geometry` call in `__init__` (`self._apply_saved_geometry()`)
with `self._sync_layout_for_edge()`. Defer real geometry to `showEvent`.

3g. Replace the `moveEvent`/`resizeEvent`/`closeEvent` geometry persistence and
`_apply_saved_geometry`/`_persist_geometry` with docking. Delete
`_apply_saved_geometry` and `_persist_geometry`; remove `moveEvent` and
`resizeEvent` overrides (no longer persisting free geometry). Add:

```python
    def showEvent(self, event):
        super().showEvent(event)
        self._apply_dock()
```

3h. Snap on drag release — in `mouseReleaseEvent`, after clearing the drag
offset, snap:

```python
    def mouseReleaseEvent(self, event):
        was_dragging = self._drag_offset is not None
        self._drag_offset = None
        if was_dragging:
            self._snap_to_nearest()
```

- [ ] **Step 4: Run the new test + the existing window-settings tests**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py tests/test_window_settings.py -v`
Expected: PASS. (If `test_window_settings.py` constructed the window relying on saved geometry, it should still pass — those tests don't assert geometry.)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_shell_window.py
git commit -m "feat: docked panel with edge snapping + spine mirroring, painter widgets"
```

---

## Task 8: Header — status pills + game menu (replace dropdown)

**Files:**
- Modify: `meister_guide/overlay/window.py` (`_build_header`, `_set_active`, `set_detected_game`, `_populate_dropdown`/`_on_manual_pick`)
- Test: `tests/test_shell_window.py` (add tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shell_window.py`:

```python
from meister_guide.db.games import Game  # dataclass: id, name, process_names, wiki_url


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
```


- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py -k game -v`
Expected: FAIL — `AttributeError: 'OverlayWindow' object has no attribute 'game_pill'`.

- [ ] **Step 3: Implement header pills + menu**

3a. Rewrite `_build_header` to use pills + a clickable game pill (QToolButton with
a menu) instead of `QLabel` indicator + `QComboBox`:

```python
    def _build_header(self) -> QWidget:
        from PySide6.QtWidgets import QToolButton, QMenu
        header = QWidget()
        header.setObjectName("Header")
        lay = QVBoxLayout(header)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(9)

        row1 = QHBoxLayout()
        word = QLabel("Meister")
        word.setObjectName("Wordmark")
        sub = QLabel("guide")
        sub.setObjectName("WordmarkSub")
        row1.addWidget(word)
        row1.addWidget(sub)
        row1.addStretch(1)
        self.hotkey_chip = QLabel(
            self._settings_repo.get("hotkey", "Alt+Insert")
            if self._settings_repo else "Alt+Insert")
        self.hotkey_chip.setObjectName("HotkeyChip")
        row1.addWidget(self.hotkey_chip)
        close = QPushButton("✕")
        close.setObjectName("CloseBtn")
        close.setFixedSize(28, 28)
        close.clicked.connect(self.hide)
        row1.addWidget(close)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(7)
        self.game_pill = QToolButton()
        self.game_pill.setObjectName("GamePill")
        self.game_pill.setPopupMode(QToolButton.InstantPopup)
        self._game_menu = QMenu(self.game_pill)
        self.game_pill.setMenu(self._game_menu)
        row2.addWidget(self.game_pill)
        row2.addStretch(1)
        lay.addLayout(row2)

        self._header = header
        self._rebuild_game_menu()
        self._update_game_pill()
        return header
```

3b. Add helpers and update the manual-pick path:

```python
    def _rebuild_game_menu(self):
        if not hasattr(self, "_game_menu"):
            return
        self._game_menu.clear()
        for game in self._games:
            act = self._game_menu.addAction(game.name)
            act.triggered.connect(lambda _=False, gid=game.id:
                                  self._on_manual_pick_game(gid))

    def _update_game_pill(self):
        if self.active_game is None:
            self.game_pill.setText("●  No game detected")
            self.game_pill.setProperty("detected", False)
        else:
            self.game_pill.setText(f"●  {self.active_game.name} detected")
            self.game_pill.setProperty("detected", True)
        # re-polish so the [detected="true"] QSS state applies
        self.game_pill.style().unpolish(self.game_pill)
        self.game_pill.style().polish(self.game_pill)

    def _on_manual_pick_game(self, game_id):
        chosen = next((g for g in self._games if g.id == game_id), None)
        if chosen is not None:
            self._set_active(chosen, manual=True)
```

3c. Update `_set_active` to drive the pill (it currently sets `game_indicator`
text + dropdown visibility). Replace its body with:

```python
    def _set_active(self, game, manual: bool):
        self.active_game = game
        self._update_game_pill()
```

3d. Update `set_games` to rebuild the menu:

```python
    def set_games(self, games):
        self._games = list(games)
        self._rebuild_game_menu()
```

3e. Delete `_populate_dropdown`, `_on_manual_pick`, and the `game_dropdown` /
`game_indicator` references (they no longer exist). `set_detected_game` stays but
now just calls `_set_active(game, manual=False)` (unchanged body is fine).

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_shell_window.py
git commit -m "feat: header status pills + game-pill menu (replaces dropdown)"
```

---

## Task 9: Tab rename/reorder + default Wiki + adaptive footer

**Files:**
- Modify: `meister_guide/overlay/window.py` (`_build_tabs`, `_build_footer`, and a footer-copy helper)
- Test: `tests/test_shell_window.py` (add tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shell_window.py`:

```python
from meister_guide.db.settings import BACKEND_OLLAMA, BACKEND_AUTO


def test_tab_order_and_default(tmp_path):
    w, repo = _window(tmp_path)
    titles = [w._tabs.tabText(i) for i in range(w._tabs.count())]
    assert titles[0] == "Wiki"
    assert titles[1] == "Ask Meister"
    assert w._tabs.currentIndex() == 0       # default landing = Wiki


def test_footer_copy_adapts_to_backend(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)
    w._refresh_footer()
    assert "no cloud" in w.footer_note.text().lower()
    repo.set("chat_backend", BACKEND_AUTO)
    repo.set("claude_api_key", "sk-x")
    w._refresh_footer()
    assert "online" in w.footer_note.text().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py -k "tab_order or footer" -v`
Expected: FAIL — title is "Chat"/"Guides", or `footer_note` missing.

- [ ] **Step 3: Implement tab reorder + footer**

3a. Rewrite `_build_tabs` to the new order/names (Wiki first, Ask Meister, ⚙):

```python
    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self._guides_index = tabs.addTab(self._build_guides_tab(), "Wiki")
        tabs.addTab(self._build_chat_tab(), "Ask Meister")
        tabs.addTab(self._build_settings_tab(), "⚙")
        tabs.setCurrentIndex(0)   # default landing = Wiki
        self._tabs = tabs
        return tabs
```

(The settings cog uses the ⚙ glyph for now; an SVG icon can replace it in
Phase 11.)

3b. Rewrite `_build_footer` to keep a reference + adaptive copy:

```python
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setFixedHeight(34)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(18, 0, 18, 0)
        self.footer_note = QLabel("")
        self.footer_note.setObjectName("FooterNote")
        lay.addWidget(self.footer_note)
        lay.addStretch(1)
        stack = QLabel("PySide6")
        stack.setObjectName("FooterStack")
        lay.addWidget(stack)
        self._refresh_footer()
        return footer

    def _refresh_footer(self):
        backend = (self._settings_repo.chat_backend()
                   if self._settings_repo is not None else BACKEND_AUTO)
        key = (self._settings_repo.claude_api_key()
               if self._settings_repo is not None else "")
        online = backend == BACKEND_CLAUDE or (backend == BACKEND_AUTO and key)
        self.footer_note.setText(
            "local-first · optional online" if online
            else "runs locally · no account · no cloud")
```

3c. Call `self._refresh_footer()` at the end of `_refresh_chat_backend` (so saving
settings updates the footer too). Add this one line after the existing body of
`_refresh_chat_backend`:

```python
        self._refresh_footer()
```

(Guard: `_refresh_chat_backend` runs during `_build_chat_tab`, which is built
AFTER `_build_tabs`’ guides tab but the footer is built after tabs. Ensure
`_build_footer` runs before any `_refresh_chat_backend` that touches
`footer_note`, OR guard with `if hasattr(self, "footer_note")`. Add the guard:)

```python
        if hasattr(self, "footer_note"):
            self._refresh_footer()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_shell_window.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_shell_window.py
git commit -m "feat: reorder/rename tabs (Wiki default) + adaptive footer copy"
```

---

## Task 10: Rewrite QSS + wire fonts in main.py

**Files:**
- Modify: `meister_guide/theme/stylesheet.py`
- Modify: `meister_guide/main.py`
- Test: full suite

- [ ] **Step 1: Rewrite the stylesheet to new tokens + objects**

```python
# meister_guide/theme/stylesheet.py
"""Builds the global QSS from the palette + loaded font families."""
from meister_guide.theme.palette import PALETTE
from meister_guide.theme import fonts


def build_stylesheet() -> str:
    p = PALETTE
    body = fonts.family("body")
    mono = fonts.family("mono")
    display = fonts.family("display")
    return f"""
    QWidget {{
        color: {p['parchment']};
        font-family: '{body}';
        font-size: 13px;
        background: transparent;
    }}
    #OverlayRoot {{ background: transparent; }}
    #Header {{ background: transparent; }}
    #Wordmark {{
        font-family: '{display}';
        font-size: 30px;
        color: {p['brass_bright']};
    }}
    #WordmarkSub {{
        font-family: '{mono}';
        font-size: 11px;
        letter-spacing: 4px;
        color: {p['parchment_ghost']};
    }}
    #HotkeyChip {{
        font-family: '{mono}';
        font-size: 10px;
        color: {p['parchment_ghost']};
        border: 1px solid rgba(200,161,74,0.22);
        border-radius: 6px;
        padding: 4px 8px;
    }}
    #CloseBtn {{
        border-radius: 7px;
        border: 1px solid rgba(200,161,74,0.25);
        background: rgba(0,0,0,0.25);
        color: {p['parchment_dim']};
    }}
    #CloseBtn:hover {{
        background: rgba(122,58,30,0.5);
        color: {p['parchment']};
        border-color: rgba(200,110,70,0.5);
    }}
    QToolButton#GamePill {{
        font-family: '{mono}';
        font-size: 10px;
        padding: 4px 9px;
        border-radius: 6px;
        border: 1px solid rgba(200,161,74,0.25);
        background: rgba(0,0,0,0.2);
        color: {p['parchment_dim']};
    }}
    QToolButton#GamePill[detected="true"] {{
        border: 1px solid rgba(120,170,90,0.4);
        background: rgba(80,130,60,0.14);
        color: {p['green_online']};
    }}
    QToolButton#GamePill::menu-indicator {{ image: none; width: 0; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        font-family: '{body}';
        font-size: 13px;
        font-weight: 600;
        background: transparent;
        color: {p['parchment_dim']};
        padding: 10px 14px;
        border: none;
    }}
    QTabBar::tab:selected {{
        color: {p['parchment']};
        border-bottom: 2px solid {p['brass_bright']};
    }}
    QPushButton {{
        background: rgba(0,0,0,0.2);
        border: 1px solid rgba(200,161,74,0.25);
        border-radius: 7px;
        padding: 6px 12px;
        color: {p['parchment']};
    }}
    QPushButton:hover {{
        background: rgba(200,161,74,0.12);
        border-color: rgba(200,161,74,0.45);
    }}
    QLineEdit {{
        background: rgba(0,0,0,0.28);
        border: 1px solid rgba(200,161,74,0.28);
        border-radius: 9px;
        padding: 8px 11px;
        color: {p['parchment']};
        font-family: '{body}';
    }}
    QTextBrowser, QListWidget {{
        background: rgba(0,0,0,0.2);
        border: 1px solid rgba(200,161,74,0.14);
        border-radius: 10px;
        color: {p['parchment_mid']};
    }}
    #Disclaimer {{
        color: {p['ink_dim']};
        font-family: '{mono}';
        font-size: 10px;
        background: transparent;
        border: none;
    }}
    #Footer {{ background: rgba(0,0,0,0.22); border-top: 1px solid rgba(200,161,74,0.16); }}
    #FooterNote, #FooterStack {{
        font-family: '{mono}';
        font-size: 10px;
        color: {p['ink_dim']};
    }}
    #FooterStack {{ color: {p['parchment_ghost']}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #4a3320; border-radius: 6px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
```

- [ ] **Step 2: Wire fonts + dock into main.py**

In `meister_guide/main.py`:

2a. Add import: `from meister_guide.theme.fonts import load_fonts`.

2b. Load fonts BEFORE building the stylesheet (stylesheet reads families):

```python
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    load_fonts()                       # register bundled fonts first
    app.setStyleSheet(build_stylesheet())
```

2c. No `dock_edge` arg needed in the constructor (the window reads it from
`settings_repo` itself). Leave the `OverlayWindow(...)` call as-is.

- [ ] **Step 3: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest -q`
Expected: PASS — all tests (baseline 143 + new ones). Fix any breakage from the
header/dropdown removal (e.g. an old test referencing `game_dropdown` or
`game_indicator` must be updated to `game_pill`).

- [ ] **Step 4: Manual visual check**

Run the app: `py -3 -m meister_guide.main` (or the project's normal launch).
Confirm against the screenshots: woodgrain panel, leather spine with studs +
stitching, brass wordmark, status pill, Wiki/Ask Meister/⚙ tabs, footer. Drag
the header to the other side and confirm it snaps + the spine mirrors. Note any
visual gaps to refine (paint values can be nudged in `painters.py`).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/theme/stylesheet.py meister_guide/main.py
git commit -m "feat: rewrite QSS to journal theme; load bundled fonts at startup"
```

---

## Task 11: Devlog + finalize

**Files:**
- Create: `devlogs/010-the-frame.md`

- [ ] **Step 1: Write the devlog**

Write `devlogs/010-the-frame.md` in the established first-person voice (see
`devlogs/009-online-first.md` for tone). Cover: the journal aesthetic, custom
painting vs QSS, docking + edge snapping with spine mirroring, bundled fonts,
header pills replacing the dropdown, the Wiki/Ask Meister/⚙ rename, and that tab
*contents* come next phase. Mention the new test count.

- [ ] **Step 2: Run the full suite one more time**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add devlogs/010-the-frame.md
git commit -m "docs: devlog 010 — the frame (shell restyle)"
```

- [ ] **Step 4: Merge the phase branch**

```bash
git checkout master
git merge --no-ff phase-10-shell-restyle -m "Merge phase-10-shell-restyle: journal-themed overlay shell"
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest -q
```

Expected: clean merge, suite green. Do NOT stage `.planning/HANDOFF.json` or
`devlogs/the-whole-build.md` at any point.

---

## Notes for the executor

- Run every test headless with `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8`.
- Never stage `.planning/HANDOFF.json` or `devlogs/the-whole-build.md`.
- Painter values are a faithful translation of the CSS but may need small visual
  nudges after the manual check in Task 10 — that is expected, not a defect.
- If an existing test references the removed `game_dropdown`/`game_indicator`,
  update it to the new `game_pill` API as part of the task that removes them.
- `Game` is a dataclass `(id, name, process_names, wiki_url)` — all positional
  fields required; pass `wiki_url=None` in fixtures.
- **Drop shadow (spec component 3) is deferred to Phase 11 polish.** A
  `QGraphicsDropShadowEffect` needs a transparent margin *inside* the top-level
  window so the blur isn't clipped, which means the visible panel would be
  smaller than the window and `dock_rect` would have to account for the shadow
  inset. That coupling isn't worth it for the shell pass; the panel reads well
  without it. Revisit once the content layout is settled.
