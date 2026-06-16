# Design — Overlay Over Fullscreen Games (Path B)

**Date:** 2026-06-16
**Status:** Approved (approach), implementation pending
**Builds on:** `meister_guide/overlay/win32_topmost.py` (the topmost fix added earlier this session)

## Problem

The overlay must appear on top when the user opens it over a running game, "like
Steam." The earlier `force_window_to_front` fix made the overlay sit above
**borderless** games, but it stays **behind** Minecraft in **fullscreen** mode.

Evidence gathered this session:
- Windowed Minecraft → overlay appears on top (fix is sound).
- Fullscreen Minecraft → overlay stays behind, and **Minecraft keeps rendering**
  (it does not minimize or change display mode).

That last point is the key: Minecraft's fullscreen is a **borderless topmost
window** rendered through the Windows compositor, not true exclusive fullscreen.
So the only thing keeping it above us is that its window sits in the "always-on-top"
(`WS_EX_TOPMOST`) z-order band, same band as ours, and it was activated more
recently.

## Approach (Path B): demote the game from the topmost band while the overlay is open

When the overlay is shown, drop the **game's** window out of the topmost band so
our (topmost + foreground) overlay sits above it. When the overlay is hidden,
restore the game's window to topmost.

This is deliberately minimal and reversible:
- We only toggle the game window's z-order band (`HWND_NOTOPMOST` / `HWND_TOPMOST`).
- We never touch its size, position, styles, or rendering.
- We only demote a window that was **already topmost** — i.e. a fullscreen game or
  another always-on-top app — and we record that so we can restore it exactly.
  Ordinary (non-topmost) apps are left untouched.
- If a future game is *truly* exclusive fullscreen (bypasses the compositor), this
  simply has no effect — no harm — and the fallback is to play windowed/borderless.

Being topmost-and-foreground is a more reliable "this is the fullscreen game"
signal than matching the detector's process, and it also covers games we haven't
catalogued. So the trigger is the window's topmost state, not the detector.

## Components

### `meister_guide/overlay/win32_topmost.py` (extend)
Add small, individually testable Win32 wrappers (all accept an injectable
`user32` for tests, no-op off Windows):
- `get_foreground_window() -> int`
- `is_window_topmost(hwnd) -> bool` — reads `WS_EX_TOPMOST` via `GetWindowLongW(GWL_EXSTYLE)`.
- `set_window_topmost(hwnd, topmost: bool)` — `SetWindowPos` with
  `HWND_TOPMOST` / `HWND_NOTOPMOST`, flags `NOMOVE|NOSIZE|NOACTIVATE`.
- Keep existing `force_window_to_front`.

### `meister_guide/overlay/window.py` (orchestrate)
- `toggle()` show branch: **before** `show()` (while the game still owns the
  foreground), capture `get_foreground_window()`; if it isn't our window and it
  is topmost, demote it and remember its handle in `self._demoted_hwnd`. Then
  `show()` + `force_window_to_front(self)`.
- `hideEvent`: if `self._demoted_hwnd` is set, restore it to topmost and clear it.
  Using `hideEvent` (not just the toggle hide branch) means the footer
  minimize/close buttons restore the game too.

## Data flow

```
Alt+Insert (overlay hidden)
  -> fg = GetForegroundWindow()            # the game
  -> if fg topmost: SetWindowPos(fg, NOTOPMOST); remember fg
  -> show(); force overlay topmost + foreground
  -> overlay now above the game

Alt+Insert (overlay visible) / minimize / close
  -> hideEvent: SetWindowPos(remembered fg, TOPMOST); forget it
  -> game restored to always-on-top fullscreen
```

## Error handling / edge cases
- Game closed while overlay open → restoring a dead HWND: `SetWindowPos` returns 0,
  harmless.
- Foreground is our own window or the desktop → skip (don't demote).
- Foreground app wasn't topmost → skip (we only restore what we demoted).
- Non-Windows / offscreen test platform → helpers no-op.

## Testing
- Unit tests with a fake `user32`:
  - `is_window_topmost` true/false from the ex-style bit.
  - `set_window_topmost(True/False)` passes the right `HWND_TOPMOST`/`HWND_NOTOPMOST`.
- Window-level z-order is GUI behavior → verified by the user via `run.bat`:
  open over fullscreen Minecraft (overlay on top, game pauses behind), close
  (game returns to fullscreen on top).

## Supported game modes (decided after testing)

Testing revealed Minecraft Java **fullscreen (F11) is a GLFW exclusive-style
window that auto-iconifies on focus loss**: once Path B let our
`SetForegroundWindow` succeed, Minecraft lost focus and minimized out of
fullscreen ("tabbed out"). No OS-level approach can keep a GLFW-fullscreen
window on screen while another window takes focus — that needs render-pipeline
injection, which is out of scope.

**Decision: support windowed / borderless-windowed only.** In those modes losing
focus does not iconify, so the overlay takes focus, the game pauses behind it,
and `Alt+Insert` dismisses it — the full Steam-like flow. The Path B code is
correct as-is for these modes (it demotes a topmost borderless game so the
overlay sits above). Users who want a seamless full-screen feel run the game
borderless (for Minecraft Java, via a borderless-window mod). Documented in
`README.md`.

## Out of scope
- DLL injection / DirectX-Vulkan-OpenGL render hooking (true exclusive / GLFW
  fullscreen overlays). Not feasible in a pure-PySide6 app.
- The visual "Steam look" (full-screen dim + centered panel) — the user is
  revamping the UI separately later.
