# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MeisterGuide. Build with: py -m PyInstaller MeisterGuide.spec
#
# datas: bundled fonts + app icon. No seed DB is bundled (the app fills guides via
# on-demand wiki fetch + free web search at runtime). To ship a prebuilt corpus,
# add ('seed/meister.db', 'seed') to datas — main.py copies it to %APPDATA% on
# first run if the user has none.
# hiddenimports: lazy-imported deps PyInstaller's static analysis can miss.

a = Analysis(
    ['meister_guide/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/fonts/Archivo.ttf', 'assets/fonts'),
        ('assets/fonts/PirataOne-Regular.ttf', 'assets/fonts'),
        ('assets/fonts/SplineSansMono.ttf', 'assets/fonts'),
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=['anthropic', 'trafilatura', 'ddgs'],
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
