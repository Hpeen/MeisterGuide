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
