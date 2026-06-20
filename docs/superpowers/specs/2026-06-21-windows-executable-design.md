# Windows executable (PyInstaller one-file) — design

**Date:** 2026-06-21
**Status:** Approved, ready for planning

## Problem

MeisterGuide currently runs only from source (`py -3 -m meister_guide.main`). To
let people try it — and to ship alongside the third Stardance devlog — it needs
to be a double-clickable Windows executable. A first-time user should get a
working app with usable Minecraft guides, without installing Python or building a
corpus by hand.

## Decisions (locked during brainstorming)

- **PyInstaller, one-file** `MeisterGuide.exe` (windowed, no console), driven by a
  committed `.spec` so the build is reproducible. One-file chosen over one-folder
  for distribution simplicity (one download, double-click).
- **Bundle a prebuilt Minecraft guide DB** so first launch works instantly and
  offline. On first run the bundled DB is copied to `%APPDATA%` only if the user
  has none; existing installs are untouched.
- **No online demo / web port.** Out of scope — the app is a native overlay
  (global hotkey, always-on-top over fullscreen games, tray, process detection)
  that cannot run in a browser. Dropped entirely.
- **Unsigned build.** Code signing is out of scope; the SmartScreen
  "unknown publisher" warning is documented in the release notes instead.

## Non-goals

- Code signing / notarization. An installer (Inno Setup/MSI) — the bare `.exe` is
  enough for a devlog. Auto-update. macOS/Linux builds. CI build automation
  (manual local build for now). Shipping corpora for non-Minecraft games.

## Components

### 1. `meister_guide/resources.py` (new)

Single place that knows about the PyInstaller bundle layout.

```
def resource_path(rel: str) -> Path:
    """Absolute path to a bundled resource. Uses PyInstaller's sys._MEIPASS when
    frozen, else the repo root. `rel` is a forward-slash relative path like
    "assets/fonts". (resources.py lives at meister_guide/resources.py, so the repo
    root is parents[1].)"""
    base = Path(getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parents[1])))
    return base / rel
```

- Frozen: `sys._MEIPASS` is the unpack dir; bundled `datas` land at their declared
  relative paths under it.
- Dev: resolves to the repo root so existing `py -3 -m meister_guide.main` runs
  unchanged.
- The dev base is computed once here; no other module hardcodes bundle paths.

### 2. `meister_guide/theme/fonts.py` — fix the one fragile path

Replace:
```
_DEFAULT_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
```
with a call through the helper:
```
from meister_guide.resources import resource_path
_DEFAULT_ASSETS = resource_path("assets/fonts")
```
`load_fonts(assets_dir=None)` keeps its injectable override (used by tests), so
only the default changes. This is the only `__file__`-relative asset path in the
codebase (verified by grep), so it's the only bundle break to fix.

### 3. First-run seed-DB copy — `meister_guide/main.py`

The DB path (`default_db_path()` → `%APPDATA%/MeisterGuide/meister.db`) already
works frozen. Add, before the first `connect(default_db_path())`:

- A pure helper `seed_db_if_missing(target: Path, seed: Path) -> bool`
  (new, in `db/database.py` next to `default_db_path`): if `target` does not
  exist and `seed` exists, create `target`'s parent and copy `seed` → `target`;
  return whether a copy happened. Idempotent and side-effect-isolated so it's
  unit-testable.
- `main.py` calls it with `target=default_db_path()`,
  `seed=resource_path("seed/meister.db")`. The bundled seed lives at `seed/` in
  the spec's `datas`. When run from source with no `seed/meister.db`, the helper
  is a no-op (returns False) and the app behaves exactly as today.

Net behavior: fresh install → instant Minecraft corpus; upgrade/existing user →
their DB is preserved; from-source dev → unchanged.

### 4. `MeisterGuide.spec` (new, repo root)

PyInstaller spec, committed for reproducibility:

- **Analysis:** entry `meister_guide/main.py`.
- **datas:**
  - `assets/fonts/Archivo.ttf`, `PirataOne-Regular.ttf`, `SplineSansMono.ttf`
    → `assets/fonts/`
  - `seed/meister.db` → `seed/` (the prebuilt Minecraft DB; see Seed DB step)
  - `assets/icon.ico` → `assets/`
- **hiddenimports:** lazy-imported deps PyInstaller's static analysis misses —
  `anthropic`, `trafilatura`, `ddgs`, and any submodules surfaced by *running the
  built exe* (determined empirically, not guessed; see Testing). `requests`,
  `psutil`, and `PySide6` are imported normally and covered by standard hooks.
- **EXE:** `name="MeisterGuide"`, `console=False`, one-file (`onefile`),
  `icon="assets/icon.ico"`.

### 5. `assets/icon.ico` (new)

A small multi-size `.ico` for the exe and tray, matching the existing
runtime-drawn "MG" mark (dark tile, light "MG"). Generated once and committed;
`main.py::_make_tray_icon` may optionally load it via `resource_path` for visual
consistency, but that is a nicety, not required for this spec.

## Seed DB step (build-time, decided then)

The spec depends on a `seed/meister.db`. Its contents are chosen at build time:

- **Preferred:** a *completed* Minecraft corpus — run **Update guides** to
  completion first (the article walk currently stalls ~"E"; it resumes and then
  runs the redirect pass). The background-download fix (hideEvent no longer
  cancels ingest) makes finishing this practical.
- **Fallback:** the current half-complete DB — testers still get instant answers
  for early-alphabet topics, and on-demand wiki fetch + free web fallback cover
  the rest at runtime (needs internet for those).

Either way, the seed file is copied into `seed/meister.db` before building; no
code differs. The seed DB is **not** committed to git (it is large and
regenerable) — it is placed locally for the build and listed in `.gitignore`.

## Build & distribution

- Build: `py -m PyInstaller MeisterGuide.spec` (PyInstaller added to a dev/build
  requirement note, not the runtime `requirements.txt`).
- Output: `dist/MeisterGuide.exe`.
- Release note text (for the devlog/download): one line that Windows SmartScreen
  will show an "unknown publisher" prompt → *More info → Run anyway*, because the
  build is unsigned.
- A short `BUILD.md` (or README section) documents the seed-DB placement and the
  build command.

## Error handling

- Missing seed DB at runtime → `seed_db_if_missing` returns False, app starts with
  an empty corpus and fills via on-demand/web fetch. No crash.
- Missing/again-unpacked fonts → `load_fonts` already tolerates missing files
  (returns whatever loaded); Qt falls back to system fonts. No crash.
- First-run copy failure (e.g. permissions) → caught and logged; app continues
  with an empty corpus rather than failing to launch.

## Testing (TDD)

**Unit (pure, no PyInstaller needed):**
- `resource_path`: returns `sys._MEIPASS`-based path when `sys._MEIPASS` is set
  (monkeypatched); returns repo-root path when it is absent.
- `seed_db_if_missing`: copies when target absent and seed present (target then
  exists, returns True); no-op when target already exists (returns False, target
  unchanged); no-op when seed absent (returns False).
- `fonts.load_fonts` default path still resolves under the assets dir (existing
  tests keep passing via the injectable `assets_dir`).

**Build verification (manual, the real artifact):**
- `py -m PyInstaller MeisterGuide.spec` produces `dist/MeisterGuide.exe`.
- Launch the exe on a clean `%APPDATA%` (no existing DB): tray icon appears,
  Alt+Insert summons the overlay, custom fonts render, the seeded Minecraft DB
  answers a question (e.g. "how do I tame a wolf") with sources.
- Re-launch with an existing DB: the seed copy is skipped (DB untouched).
- Any `ModuleNotFoundError` on launch feeds back into `hiddenimports`; rebuild
  until the exe runs clean.

## Build approach

One feature branch (`windows-executable`), TDD for the pure helpers, then the
`.spec` + build verification. Subagent-driven with per-task spec + quality review
and a final whole-branch review, then `finishing-a-development-branch`. Run tests
with `py -m pytest -q`.
