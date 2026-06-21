# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MeisterGuide. Build with: py -m PyInstaller MeisterGuide.spec
#
# datas: bundled fonts + app icon. No seed DB is bundled (the app fills guides via
# on-demand wiki fetch + free web search at runtime). To ship a prebuilt corpus,
# add ('seed/meister.db', 'seed') to datas — main.py copies it to %APPDATA% on
# first run if the user has none.
# hiddenimports: lazy-imported deps PyInstaller's static analysis can miss.
from PyInstaller.utils.hooks import collect_all

_datas = [
    ('assets/fonts/Archivo.ttf', 'assets/fonts'),
    ('assets/fonts/PirataOne-Regular.ttf', 'assets/fonts'),
    ('assets/fonts/SplineSansMono.ttf', 'assets/fonts'),
    ('assets/icon.ico', 'assets'),
]
_binaries = []
_hiddenimports = ['anthropic', 'trafilatura', 'ddgs']

# trafilatura (and its data-bearing deps) ship config + stoplist files and
# lazy submodules that PyInstaller misses by default — without them extract()
# raises "No option 'min_extracted_size'" at runtime. collect_all bundles the
# data, binaries, and submodules so the parse path works in the frozen exe.
for _pkg in ('trafilatura', 'justext', 'courlan', 'htmldate'):
    _d, _b, _h = collect_all(_pkg)
    _datas += _d
    _binaries += _b
    _hiddenimports += _h

a = Analysis(
    ['meister_guide/main.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MeisterGuide',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)

# Mirror the fresh build into the user's launch folder so double-clicking
# "Launch from here/MeisterGuide.exe" never runs a stale binary against a
# migrated DB. Best-effort: a warning (not a build failure) if the file is locked.
import os
import shutil

_built = os.path.join(DISTPATH, "MeisterGuide.exe")
_launch_dir = os.path.join(SPECPATH, "Launch from here")
try:
    os.makedirs(_launch_dir, exist_ok=True)
    shutil.copyfile(_built, os.path.join(_launch_dir, "MeisterGuide.exe"))
    print("Copied MeisterGuide.exe to 'Launch from here/'")
except OSError as exc:
    print(f"WARNING: could not update 'Launch from here/': {exc}")
