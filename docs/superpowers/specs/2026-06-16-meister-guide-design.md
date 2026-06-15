# Meister Guide — Design Doc

Date: 2026-06-16
Status: Approved

## What we're building

**Meister Guide** is a Windows desktop gaming companion overlay. It stores scraped
game guides offline and serves them two ways: a manual offline guide browser, and a
local AI assistant named **Meister** (powered by Ollama). Beta target: single-player
players who want in-game help without alt-tabbing. Built for the Stardance challenge,
so each phase ships with a playful build-diary devlog.

This doc captures the decisions that the original product spec left open or that need
pinning down. The product spec (features, color palette, SQLite schema, Ollama
templates) is taken as the source of truth for everything not restated here.

## Locked decisions

- **Tech stack: Python + PySide6.** Most reliable path on Windows for the hard parts
  (global hotkey over fullscreen, process detection, scraping) with the fewest moving
  parts for a solo build.
- **Delivery: phased / MVP-first.** Five runnable slices, each with a devlog.
- **Default hotkey: `Alt + Insert`** (user-rebindable in Settings).
- **No Claude API in beta.** Settings shows it as a greyed-out "Coming in a future
  version" stub.

## Architecture

Single Python app, packaged later with PyInstaller. The Windows-native bits stay
native (no embedded Chromium) for overlay reliability.

- **Overlay UI — pure PySide6 widgets + QSS.** Not QWebEngineView. Qt Style Sheets
  cover the full "rustic workshop" look: wood-grain `background-image`, custom 6px
  scrollbars, the 4px burnt-sienna left "spine", chat bubbles as styled `QFrame`s,
  amber active-tab underline. Keeping it native keeps the transparent + always-on-top
  window solid over fullscreen games — embedding a web view would fight that.
- **Global hotkey — native Win32 `RegisterHotKey` via `ctypes`,** caught through a
  `QAbstractNativeEventFilter` handling `WM_HOTKEY`. This survives fullscreen games
  where higher-level hooks drop. Rebinding from Settings unregisters and re-registers.
- **RAG retrieval — SQLite FTS5 full-text search,** not an embedding model. Fully
  offline, no extra deps, fast. Top-3 matching guide pages are truncated (~500 tokens
  each) and injected into Meister's system prompt.
- **Game detection — `psutil` process poll on a `QTimer`,** every 10s, silent. Matches
  configured process names; sets active game context; manual dropdown fallback.
- **Scraper — `requests` + `BeautifulSoup` on a background `QThread`,** reports progress
  to a progress bar via Qt signals. Polite rate-limiting (small delay between requests)
  and a page cap so a sync never hammers the wiki.
- **Ollama client — `requests` streaming** to `http://localhost:11434`. Detect models
  via `/api/tags`; stream chat via `/api/chat`.

## Module layout

```
meister_guide/
  main.py            app entry, tray, hotkey, window management
  overlay/           OverlayWindow + Chat / Guides / Settings tab widgets
  db/                sqlite layer + schema + FTS5 + migrations
  scraper/           wiki fetch + clean + store (background QThread)
  ai/                Ollama client (stream) + RAG context builder
  detector/          psutil process poll (QTimer)
  theme/             meister.qss + wood-grain asset + palette constants
  assets/icons/      tray + Meister avatar
docs/superpowers/specs/   this design doc
devlogs/             one playful devlog per phase (Stardance entries)
ARCHITECTURE.md  README.md  requirements.txt
```

## Data

- SQLite at `%APPDATA%\MeisterGuide\meister.db`.
- Schema per product spec: `games`, `guides`, `chat_sessions`, `chat_messages`,
  `settings` (key-value). Plus an FTS5 virtual table mirroring `guides(title, content)`
  for offline search and RAG.
- Minecraft preloaded: process names `javaw.exe`, `Minecraft.exe`,
  `MinecraftLauncher.exe`; wiki `https://minecraft.wiki`.

## Phasing (each phase = runnable + a devlog)

1. **Shell** — tray (Show / Settings / Quit + double-click toggle); `Alt+Insert` toggles
   a transparent, always-on-top, draggable overlay that remembers size/position; footer
   X + minimize-to-tray. Full rustic QSS theme applied here so later phases inherit it.
2. **Data + detection** — SQLite schema + settings KV + Minecraft preloaded; psutil
   poller; "Playing: Minecraft" indicator + manual dropdown fallback.
3. **Scraper + Guides tab** — background scrape of minecraft.wiki with progress bar,
   clean-text storage, offline FTS5 search with highlighted excerpts + readable detail
   panel with greyed-out source URL.
4. **Chat + RAG** — Ollama detect/list models, streaming chat bubbles, RAG context
   injection, sessions + history panel, the friendly "needs Ollama" error.
5. **Settings + polish** — hotkey rebind, opacity/size/always-on-top, model picker,
   greyed-out Claude API stub, data tools (open DB folder, clear chat, re-sync),
   final theme polish.

## Smaller choices

- **Fonts fall back gracefully**: Palatino Linotype / Book Antiqua → Georgia → serif if
  not installed; Segoe UI for compact UI labels; Courier New for recipes/IDs.
- **Icons**: outline style (Lucide/Feather-like) rendered in amber/brass; ⚒ fallback for
  the Meister avatar if an SVG isn't available.
- **Devlogs**: short, fun, first-person build-diary voice — informative about what got
  built and what broke. No emojis.

## Non-goals (beta)

No Claude API, no cloud sync, no multiplayer, no screenshot capture, no plugin system.

## Definition of done

Per the product spec's 9-point checklist: silent tray launch; `Alt+Insert` toggles over
running Minecraft; auto-detect + manual select; sync scrapes the wiki into SQLite;
offline search works; Meister answers "How do I craft a diamond pickaxe?" step-by-step
using guide context; chat history saved/browseable; settings rebind hotkey + pick model;
data survives restart.
