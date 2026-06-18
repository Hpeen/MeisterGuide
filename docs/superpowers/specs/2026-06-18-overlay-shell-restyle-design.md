# Phase 10 — Overlay Shell & Theme Foundation (design)

**Date:** 2026-06-18
**Status:** approved (pending written-spec review)
**Source of truth for visuals:** `Meister Guide overlay design/design_handoff_meister_guide/README.md`
and the three screenshots + `Meister Guide.dc.html` prototype in that folder.

## Goal

Re-skin the overlay *shell* — the frame around the tabs — to the "carpenter's
guild journal" design: a charred-walnut grain panel with a burnt-sienna leather
spine, brass headings, parchment text. Phase 10 delivers the frame and the new
window behaviour; the **tab contents** (Wiki list + article reader, Ask Meister
chat bubbles, Settings model picker) keep their current functional widgets and
only inherit the new skin. Restyling tab contents and adding the new screens is
**Phase 11**.

This is the first of a two-phase restyle (decided with the user):
- **Phase 10 (this spec):** shell, fonts, docking/snapping, header/footer/tab bar.
- **Phase 11:** Wiki/Ask Meister/Settings content + new article-reader view.

## Decisions locked with the user

- **Window model:** docked panel, **draggable/snappable to either screen edge**
  (not free-floating; not single-edge).
- **Online/offline posture:** middle ground. Copy is honest and *adaptive* to the
  active backend, not absolutist "nothing leaves this machine". (See
  `[[backend-online-first]]` memory — Phase 9 made Auto the default.)
- **Fonts:** fetch + bundle the three OFL families into the repo.
- **Rendering:** Option A — custom `paintEvent` with layered `QPainter`, faithful
  to the handoff's CSS gradient stack (not pre-rendered textures).
- **Game dropdown:** keep manual override, moved behind a clickable game pill menu
  (the mockup drops the always-visible dropdown).
- **Default landing tab:** Wiki.
- **Disclaimer bar:** removed from the persistent shell (was a one-time tip).

## Non-goals (Phase 10)

- Article-reader view, chat-bubble layout, source chips, model-picker rows,
  stat cards, cloud toggle UI — all Phase 11.
- Changing any backend / RAG / ingestion behaviour.
- Manual window resizing (the docked panel is fixed-width).

## Components

### 1. Design tokens — `theme/palette.py`
Expand `PALETTE` to the handoff's full token set: walnut base/mid/light; spine
top/mid/bottom; the brass ramp (bright/mid/dark/deep) + border alphas; parchment
variants (primary/mid/dim/muted/ghost); ink-dim; user/AI bubble bg+border;
green-online; warning. **Keep all existing keys** (`background`, `panel`,
`accent_primary`, etc.) as aliases pointing at the nearest new token so current
`stylesheet.py` references keep working. Painters and QSS both read from here.

### 2. Fonts — new `theme/fonts.py` + `assets/fonts/`
- Fetch `Pirata One`, `Archivo`, `Spline Sans Mono` `.ttf` files into
  `assets/fonts/` (OFL — redistributable in-repo).
- `load_fonts()` registers each via `QFontDatabase.addApplicationFont`, called
  from `main.py` before building the UI. Returns a dict of role → resolved family
  name. If a file is missing or fails to register, fall back to
  serif / "Segoe UI" / "Consolas" so the app never hard-fails.
- A small `FONT_ROLES` map (`display`→Pirata One, `body`→Archivo, `mono`→Spline
  Sans Mono) so `stylesheet.py` and widgets reference roles, not literals.

### 3. Custom-painted shell — `theme/painters.py` (or extend `theme/woodgrain.py`)
- **Body panel painter:** draws the walnut base diagonal gradient + four
  `repeating-linear-gradient` grain layers + edge vignette + inner highlight,
  clipped to a 13px-rounded rect on the outer side. Implemented as the
  `OverlayRoot` widget's `paintEvent` (or a dedicated `PanelWidget`).
- **Spine painter:** fixed 30px width; leather vertical gradient
  (`#8a4423 → #6e3318 → #7a3a1e`), centred dotted stitching, two 8×8px brass
  studs (radial gradient) inset 18px top/bottom, inner shadows; 13px rounded
  corners on its side. Extends the existing `Spine` widget.
- **Drop shadow:** `QGraphicsDropShadowEffect` on the panel (blur ~60, y-offset
  ~30, ~55% black). Needs transparent margin around the panel inside the
  top-level translucent window so the shadow isn't clipped.

### 4. Window behaviour — docking + snapping — `config/dock.py` (new) + `window.py`
- Frameless + translucent + always-on-top + Tool (already set today).
- **Geometry:** fixed width **432px** (30 spine + 402 body). Height = available
  screen geometry height − 18px top − 18px bottom. Horizontal: 18px gap from the
  docked edge.
- **Pure helper `dock_rect(screen_geometry, edge) -> QRect`** computes the panel
  rectangle from the current screen geometry + edge (`"left"`/`"right"`). Unit-
  testable without a display.
- **Pure helper `nearest_edge(window_center_x, screen_geometry) -> str`** for snap
  on drag-release. Unit-testable.
- **Drag:** header drag moves the window (existing mechanism); on
  `mouseReleaseEvent`, compute `nearest_edge`, persist it, and animate/settle to
  `dock_rect`.
- **Mirroring:** spine always faces *inward* (toward screen centre); body hugs the
  screen edge. Docked right → spine on left (as in mockup). Docked left → layout
  and corner rounding mirror. A `_dock_edge` field drives both geometry and which
  side the spine + rounded corners render on.
- **Persistence:** new setting `dock_edge` via `SettingsRepo` (default `"right"`).
  Replaces today's x/y/w/h geometry persistence for this window. Recompute on
  `showEvent` and on screen-resolution / screen-count change.
- **Multi-monitor:** dock to the edges of the screen the overlay currently
  occupies (`QGuiApplication.screenAt`), falling back to the primary screen.

### 5. Header — `window.py`
- Row 1: "Meister" wordmark (display font, brass) + "guide" mono sub-label +
  spacer + live hotkey chip (reads the stored hotkey spec) + close ✕ (hides).
- Row 2 status pills, driven by the existing detector via `set_detected_game`:
  - Game-detected pill: green dot + "<Game> detected".
  - Process/version pill when known.
  - "No game detected" neutral state otherwise.
- **Manual override:** the game pill is a clickable menu (`QToolButton` +
  `QMenu`) listing known games; selecting one calls the existing manual-pick path.
  This replaces the always-visible `game_dropdown`.

### 6. Tab bar + footer — `window.py`
- Reorder/rename tabs to **Wiki** (was "Guides") · **Ask Meister** (was "Chat") ·
  **⚙** (icon-only Settings, Material cog). Update the stored tab indices
  (`_guides_index` etc.) accordingly.
- Active tab: brass-gradient underline (`#b8923f → #e0bd66`) with glow; inactive
  parchment-dim, active parchment.
- **Default landing tab = Wiki.**
- Footer: adaptive copy — local-only backend → "runs locally · no cloud";
  online-enabled → "local-first · optional online". "PySide6" label on the right.

## Data flow / wiring

- `main.py`: call `load_fonts()` before `OverlayWindow` construction; read
  `dock_edge` from `SettingsRepo` and pass to the window (alongside the existing
  `settings_repo` + `hotkey`).
- `OverlayWindow`: gains `_dock_edge`, the dock/sners helpers, the painters, and
  the header pill/menu. No changes to chat/guides/ingest logic.
- All colours and fonts resolve through `palette.py` + `fonts.py`; no literals in
  widget code.

## Error / edge handling

- Missing font file → fallback family, app still runs.
- Unknown/garbage `dock_edge` value → default to `"right"`.
- Screen smaller than the panel / resolution change → recompute `dock_rect`;
  clamp height to available geometry.
- Painters must not raise on zero-size or first paint (construction smoke-test).

## Testing

Pure-logic / state, unit-tested headless (`QT_QPA_PLATFORM=offscreen`):
- `dock_rect(screen, edge)` → correct width (432), 18px margins, full height, for
  both edges.
- `nearest_edge(center_x, screen)` → left/right by midpoint.
- `dock_edge` persistence round-trips via `SettingsRepo` (incl. bad-value
  default).
- `load_fonts()` falls back cleanly when a font file is absent (temp dir).
- Header: `set_detected_game(game)` / `None` updates pill text + state; game-pill
  menu triggers the manual-pick path.
- Tab order/names + default landing tab = Wiki.
- Smoke: constructing the window + invoking the panel/spine `paintEvent` on a
  `QPixmap` doesn't raise.

Visual fidelity (gradients, stitching, studs, shadow) is verified by **running
the app** and comparing to the screenshots — not asserted pixel-by-pixel.

## Files touched

| File | Change |
|---|---|
| `theme/palette.py` | Expand to full token set; keep old keys as aliases |
| `theme/fonts.py` | **new** — fetch/register fonts, role map, fallbacks |
| `assets/fonts/*.ttf` | **new** — bundled OFL fonts |
| `theme/painters.py` | **new** (or extend `woodgrain.py`) — panel + spine painters |
| `theme/stylesheet.py` | Rewrite QSS to new tokens/fonts/objects |
| `config/dock.py` | **new** — `dock_rect`, `nearest_edge` pure helpers |
| `meister_guide/overlay/window.py` | Docking/snapping, header pills+menu, tab rename/reorder, footer, wire painters |
| `meister_guide/main.py` | Load fonts; read+pass `dock_edge` |
| `meister_guide/db/settings.py` | `dock_edge` default |
| `tests/…` | New tests per above |

## Devlog

`devlogs/010-the-frame.md` (working title), matching the established first-person
style.
