# Building MeisterGuide.exe

## Run from source
1. Install Python 3.11 or newer.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python -m meister_guide.main`

Run the tests with `pytest -q`.

## Prerequisites
- Python 3 with the runtime deps installed (`py -m pip install -r requirements.txt`).
- Build deps: `py -m pip install -r requirements-build.txt`.

## Steps
1. Generate the icon (once, or after changing the design):
   `py tools/make_icon.py`
2. Build: `py -m PyInstaller MeisterGuide.spec`
3. Ship `dist/MeisterGuide.exe`.

The build also copies the fresh exe to `Launch from here/MeisterGuide.exe` (the
local double-click launch point) so you never run a stale binary against a
DB that a newer build has already migrated. Close any running instance before
building, or the copy is skipped with a warning (the `dist/` build still succeeds).

## Bundling a prebuilt corpus (optional)
The default build ships **no** seed DB — the app fills guides via on-demand wiki
fetch + free web search at runtime (needs internet for the first answer on a
topic). To bundle a ready-made corpus for instant/offline answers:
1. Place the DB at `seed/meister.db` (e.g. finish the in-app **Update guides**
   download, then copy `%APPDATA%\MeisterGuide\meister.db`).
2. Add `('seed/meister.db', 'seed')` to the `datas` list in `MeisterGuide.spec`.
3. Rebuild. On first run it is copied to `%APPDATA%` only if the user has none.

## First run
On first launch the bundled `seed/meister.db` is copied to
`%APPDATA%\MeisterGuide\meister.db` only if the user has none. Existing installs
keep their data.

## Note for testers
The exe is unsigned, so Windows SmartScreen shows an "unknown publisher" prompt:
click **More info -> Run anyway**.
