# Building MeisterGuide.exe

## Prerequisites
- Python 3 with the runtime deps installed (`py -m pip install -r requirements.txt`).
- Build deps: `py -m pip install -r requirements-build.txt`.

## Steps
1. Generate the icon (once, or after changing the design):
   `py tools/make_icon.py`
2. Place the prebuilt guide DB at `seed/meister.db`. Either finish the in-app
   **Update guides** download and copy `%APPDATA%\MeisterGuide\meister.db`, or
   copy the current DB as-is. (To build without a bundled corpus, remove the
   `seed/meister.db` line from `MeisterGuide.spec` — the app then fills guides via
   on-demand/web fetch at runtime.)
3. Build: `py -m PyInstaller MeisterGuide.spec`
4. Ship `dist/MeisterGuide.exe`.

## First run
On first launch the bundled `seed/meister.db` is copied to
`%APPDATA%\MeisterGuide\meister.db` only if the user has none. Existing installs
keep their data.

## Note for testers
The exe is unsigned, so Windows SmartScreen shows an "unknown publisher" prompt:
click **More info -> Run anyway**.
